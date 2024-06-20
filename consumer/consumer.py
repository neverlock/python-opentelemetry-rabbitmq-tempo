import pika
import json
import requests
import os
from opentelemetry import trace, propagate, context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import SpanContext, set_span_in_context
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.instrumentation.pika import PikaInstrumentor

# Setup OpenTelemetry
resource = Resource.create({
    "service.name": "consumer"  # Set your service name here
})
provider = TracerProvider(resource=resource)
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(span_processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)
b3_format = B3MultiFormat()
propagate.set_global_textmap(b3_format)

# Instrument Pika
PikaInstrumentor().instrument()

def callback(ch, method, properties, body):
    message = json.loads(body)

    print("Received headers:")
    for key, value in properties.headers.items():
        print(f" - {key}: {value}")

    # Extract trace context from headers
    headers = properties.headers
    ctx = propagate.extract(headers)
    
    with tracer.start_as_current_span("process_task", context=ctx) as span:
        span.set_attribute("message", message['message'])
        span.set_attribute("custom_attribute", "custom_value")
        span.add_event("custom_event", {"event_attr": "event_value"})

        headers = {}
        propagate.inject(headers)
        
        response = requests.post("http://next_api:8001/next_api", json=message, headers=headers)
        span.set_attribute("response_status", response.status_code)
        
        print("After do job:")
        print_span_data(trace.get_current_span())
    
    ch.basic_ack(delivery_tag=method.delivery_tag)

def print_span_data(span):
    if isinstance(span, trace.NonRecordingSpan):
        print("NonRecordingSpan, no data to print")
        return
    trace_id = format(span.get_span_context().trace_id, 'x')
    print(f"Trace ID: {trace_id}")
    print(f"Span name: {span.name}")
    print("Attributes:")
    for key, value in span.attributes.items():
        print(f" - {key}: {value}")
    print("Events:")
    for event in span.events:
        print(f" - {event.name}")
        for key, value in event.attributes.items():
            print(f"   - {key}: {value}")

def main():
    url = os.environ.get('CLOUDAMQP_URL', 'amqp://guest:guest@rabbitmq/%2f')
    connection = pika.BlockingConnection(pika.URLParameters(url))
    channel = connection.channel()
    channel.queue_declare(queue='task_queue', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='task_queue', on_message_callback=callback)
    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()

if __name__ == "__main__":
    main()
