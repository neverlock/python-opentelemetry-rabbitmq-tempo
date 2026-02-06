from fastapi import FastAPI
import pika
import json
import os
from opentelemetry import trace, propagate
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from pydantic import BaseModel
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE, DEPLOYMENT_ENVIRONMENT
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.trace import SpanKind
from opentelemetry.semconv.trace import SpanAttributes

# Setup OpenTelemetry with comprehensive resource attributes
resource = Resource.create({
    SERVICE_NAME: "producer",
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

# Use B3 propagator for trace context
b3_format = B3MultiFormat()
propagate.set_global_textmap(b3_format)

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)

class TaskMessage(BaseModel):
    message: str

connection = None
channel = None

@app.on_event("startup")
async def startup_event():
    # Initialize connection on startup
    get_channel()

@app.on_event("shutdown")
async def shutdown_event():
    global connection
    if connection and not connection.is_closed:
        connection.close()

def get_channel():
    global connection, channel
    
    url = os.environ.get('CLOUDAMQP_URL', 'amqp://guest:guest@rabbitmq/%2f')
    
    if connection is None or connection.is_closed:
        print(f"Connecting to RabbitMQ at {url}")
        try:
            connection = pika.BlockingConnection(pika.URLParameters(url))
        except Exception as e:
            print(f"Failed to connect to RabbitMQ: {e}")
            raise e
            
    if channel is None or channel.is_closed:
        print("Creating new channel")
        channel = connection.channel()
        channel.queue_declare(queue='task_queue', durable=True)
        
    return channel

@app.post("/send_task/")
async def send_task(task: TaskMessage):
    tracer = trace.get_tracer(__name__)
    
    # Create a PRODUCER span for message publishing
    with tracer.start_as_current_span(
        "send_task_to_queue",
        kind=SpanKind.PRODUCER
    ) as span:
        try:
            # Ensure we have a valid channel
            ch = get_channel()
            
            # Add messaging-specific attributes for service graph
            span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "rabbitmq")
            span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, "task_queue")
            span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_KIND, "queue")
            span.set_attribute("peer.service", "consumer")
            span.set_attribute("message.content", task.message)
            
            # Inject trace context into headers
            headers = {}
            propagate.inject(headers)
            
            print(f"Producer - Sending message with trace context: {headers}")
            print_span_data(span)
            
            # Publish message to RabbitMQ with trace context
            ch.basic_publish(
                exchange='',
                routing_key='task_queue',
                body=json.dumps({'message': task.message}),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                    headers=headers
                ))
            
            span.add_event("message_published", {
                "queue": "task_queue",
                "message_size": len(task.message)
            })
            
            return {
                "status": "Message sent",
                "trace_id": format(span.get_span_context().trace_id, 'x')
            }
        except Exception as e:
            print(f"Error sending message: {e}")
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            span.record_exception(e)
            # Force close connection to trigger reconnect next time
            if connection and not connection.is_closed:
                try:
                    connection.close()
                except:
                    pass
            raise e

@app.post("/send_task_failed/")
async def send_task_failed(task: TaskMessage):
    tracer = trace.get_tracer(__name__)
    
    with tracer.start_as_current_span(
        "send_task_failed",
        kind=SpanKind.PRODUCER
    ) as span:
        try:
            # Ensure we have a valid channel
            ch = get_channel()
            
            # Add attributes
            span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "rabbitmq")
            span.set_attribute("peer.service", "consumer")
            span.set_attribute("triggered_error", True)
            
            headers = {}
            propagate.inject(headers)
            
            # Send message with force_error flag
            message_body = {
                'message': task.message,
                'force_error': True
            }
            
            print(f"Producer - Sending FAILED message with trace context: {headers}")
            
            ch.basic_publish(
                exchange='',
                routing_key='task_queue',
                body=json.dumps(message_body),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    headers=headers
                ))
            
            span.add_event("message_published_failed", {
                "queue": "task_queue",
                "triggered_error": True
            })
                
            return {
                "status": "Message sent (expecting failure in consumer)",
                "trace_id": format(span.get_span_context().trace_id, 'x')
            }
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise e

def print_span_data(span):
    trace_id = format(span.get_span_context().trace_id, 'x')
    span_id = format(span.get_span_context().span_id, 'x')
    print(f"Trace ID: {trace_id}")
    print(f"Span ID: {span_id}")
    print(f"Span name: {span.name}")
    print("Attributes:")
    if hasattr(span, 'attributes') and span.attributes:
        for key, value in span.attributes.items():
            print(f"  - {key}: {value}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
