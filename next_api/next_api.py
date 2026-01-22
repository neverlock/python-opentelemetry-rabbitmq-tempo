from fastapi import FastAPI, Request
import os
from opentelemetry import trace, context, propagate
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE, DEPLOYMENT_ENVIRONMENT
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.trace import SpanKind
from opentelemetry.semconv.trace import SpanAttributes

# Setup OpenTelemetry with comprehensive resource attributes
resource = Resource.create({
    SERVICE_NAME: "next_api",
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

@app.post("/next_api")
async def next_api(request: Request):
    print("\n" + "="*50)
    print("Next API - Received request")
    print("="*50)
    
    # Get current span (created automatically by FastAPIInstrumentor)
    current_span = trace.get_current_span()
    
    # Add additional attributes
    if current_span and not isinstance(current_span, trace.NonRecordingSpan):
        current_span.set_attribute(SpanAttributes.HTTP_METHOD, "POST")
        current_span.set_attribute(SpanAttributes.HTTP_ROUTE, "/next_api")
        current_span.set_attribute("custom.attribute", "next_api_processing")
        
        print("Request headers:")
        for key, value in request.headers.items():
            if key.lower() in ['x-b3-traceid', 'x-b3-spanid', 'x-b3-sampled']:
                print(f"  - {key}: {value}")
        
        print_span_data(current_span)
        
        # Simulate some processing
        current_span.add_event("processing_request")
        
        # You could add business logic here
        body = await request.json()
        message = body.get('message', '')
        
        current_span.set_attribute("request.message", message)
        current_span.add_event("request_processed", {
            "message_length": len(message)
        })
        
        print("="*50 + "\n")
        
        return {
            "message": "This is the next API",
            "received_message": message,
            "trace_id": format(current_span.get_span_context().trace_id, 'x')
        }
    
    return {"message": "This is the next API (no active span)"}

def print_span_data(span):
    if isinstance(span, trace.NonRecordingSpan):
        print("NonRecordingSpan, no data to print")
        return
    
    trace_id = format(span.get_span_context().trace_id, 'x')
    span_id = format(span.get_span_context().span_id, 'x')
    print(f"Trace ID: {trace_id}")
    print(f"Span ID: {span_id}")
    print(f"Span name: {span.name}")
    
    if hasattr(span, 'attributes') and span.attributes:
        print("Attributes:")
        for key, value in span.attributes.items():
            print(f"  - {key}: {value}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
