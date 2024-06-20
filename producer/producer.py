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
from opentelemetry.sdk.resources import Resource
from opentelemetry.propagators.b3 import B3MultiFormat

# Setup OpenTelemetry
resource = Resource.create({
    "service.name": "producer"  # Set your service name here
})
provider = TracerProvider(resource=resource)
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(span_processor)
trace.set_tracer_provider(provider)
b3_format = B3MultiFormat()
propagate.set_global_textmap(b3_format)

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)

class TaskMessage(BaseModel):
    message: str

@app.on_event("startup")
async def startup_event():
    global connection, channel
    url = os.environ.get('CLOUDAMQP_URL', 'amqp://guest:guest@rabbitmq/%2f')
    connection = pika.BlockingConnection(pika.URLParameters(url))
    channel = connection.channel()
    channel.queue_declare(queue='task_queue', durable=True)

@app.on_event("shutdown")
async def shutdown_event():
    connection.close()

@app.post("/send_task/")
async def send_task(task: TaskMessage):
    with trace.get_tracer(__name__).start_as_current_span("send_task") as span:
        span.set_attribute("custom_attribute", "custom_value")
        span.add_event("custom_event", {"event_attr": "event_value"})
        
        headers = {}
        propagate.inject(headers)

        print_span_data(span)
        
        channel.basic_publish(
            exchange='',
            routing_key='task_queue',
            body=json.dumps({'message': task.message}),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
                headers=headers
            ))
        return {"status": "Message sent"}

def print_span_data(span):
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
