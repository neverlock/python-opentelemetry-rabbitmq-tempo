import pika
import json
import requests
import os
from opentelemetry import trace, propagate, context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE, DEPLOYMENT_ENVIRONMENT
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.trace import SpanKind
from opentelemetry.semconv.trace import SpanAttributes

# Setup OpenTelemetry with comprehensive resource attributes
resource = Resource.create({
    SERVICE_NAME: "consumer",
    SERVICE_NAMESPACE: "messaging-demo",
    DEPLOYMENT_ENVIRONMENT: "development",
    "service.version": "1.0.0",
})

provider = TracerProvider(resource=resource)
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(span_processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

# Use B3 propagator for trace context
b3_format = B3MultiFormat()
propagate.set_global_textmap(b3_format)

# Instrument requests library for automatic HTTP client tracing
RequestsInstrumentor().instrument()

def callback(ch, method, properties, body):
    message = json.loads(body)
    
    print("\n" + "="*50)
    print("Consumer - Received message from RabbitMQ")
    print("="*50)
    
    # Extract trace context from RabbitMQ message headers
    headers = properties.headers if properties.headers else {}
    print(f"Received headers: {headers}")
    
    # Extract context from headers
    ctx = propagate.extract(headers)
    
    # Create a CONSUMER span linked to the producer's trace
    with tracer.start_as_current_span(
        "process_task_from_queue",
        context=ctx,
        kind=SpanKind.CONSUMER
    ) as consumer_span:
        # Add messaging-specific attributes
        consumer_span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "rabbitmq")
        consumer_span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, "task_queue")
        consumer_span.set_attribute(SpanAttributes.MESSAGING_OPERATION, "process")
        consumer_span.set_attribute("message.content", message.get('message', ''))
        
        # Check if this message is meant to trigger an error
        if message.get('force_error'):
            error_msg = f"Simulated error for message: {message.get('message')}"
            print(f"Consumer - Triggering simulated error: {error_msg}")
            
            # Record exception in span
            exception = ValueError(error_msg)
            consumer_span.record_exception(exception)
            consumer_span.set_status(trace.Status(trace.StatusCode.ERROR))
            
            # Ack anyway so we don't retry forever in this demo
            ch.basic_ack(delivery_tag=method.delivery_tag)
            raise exception
            
        print_span_data(consumer_span)
        
        # Create a nested CLIENT span for HTTP request to next_api
        with tracer.start_as_current_span(
            "call_next_api",
            kind=SpanKind.CLIENT
        ) as client_span:
            client_span.set_attribute(SpanAttributes.HTTP_METHOD, "POST")
            client_span.set_attribute(SpanAttributes.HTTP_URL, "http://next_api:8001/next_api")
            client_span.set_attribute("peer.service", "next_api")
            
            # Prepare headers for HTTP request with trace context
            request_headers = {
                'Content-Type': 'application/json'
            }
            # Inject current trace context into HTTP headers
            propagate.inject(request_headers)
            
            print(f"\nConsumer - Calling next_api with headers: {request_headers}")
            
            try:
                # Make HTTP request to next_api (auto-instrumented by RequestsInstrumentor)
                response = requests.post(
                    "http://next_api:8001/next_api",
                    json=message,
                    headers=request_headers,
                    timeout=10
                )
                
                client_span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, response.status_code)
                consumer_span.set_attribute("next_api.response_status", response.status_code)
                
                print(f"Consumer - Response status: {response.status_code}")
                
                if response.status_code == 200:
                    consumer_span.add_event("next_api_success")
                else:
                    consumer_span.add_event("next_api_error", {
                        "status_code": response.status_code
                    })
                    
            except Exception as e:
                print(f"Consumer - Error calling next_api: {e}")
                client_span.set_attribute("error", True)
                client_span.record_exception(e)
                consumer_span.add_event("next_api_exception", {
                    "exception": str(e)
                })
        
        consumer_span.add_event("message_processed")
        print("="*50 + "\n")
    
    # Acknowledge the message
    ch.basic_ack(delivery_tag=method.delivery_tag)

def print_span_data(span):
    if isinstance(span, trace.NonRecordingSpan):
        print("NonRecordingSpan, no data to print")
        return
    
    trace_id = format(span.get_span_context().trace_id, 'x')
    span_id = format(span.get_span_context().span_id, 'x')
    print(f"Trace ID: {trace_id}")
    print(f"Span ID: {span_id}")
    print(f"Span name: {span.name}")
    print(f"Span kind: {span.kind}")
    
    if hasattr(span, 'attributes') and span.attributes:
        print("Attributes:")
        for key, value in span.attributes.items():
            print(f"  - {key}: {value}")

def main():
    url = os.environ.get('CLOUDAMQP_URL', 'amqp://guest:guest@rabbitmq/%2f')
    print(f"Consumer - Connecting to RabbitMQ: {url}")
    
    connection = pika.BlockingConnection(pika.URLParameters(url))
    channel = connection.channel()
    channel.queue_declare(queue='task_queue', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='task_queue', on_message_callback=callback)
    
    print(' [*] Consumer waiting for messages. To exit press CTRL+C')
    channel.start_consuming()

if __name__ == "__main__":
    main()
