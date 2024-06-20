from fastapi import FastAPI, Request
import os
from opentelemetry import trace, context, propagate
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.propagators.b3 import B3MultiFormat

# Setup OpenTelemetry
resource = Resource.create({
    "service.name": "next_api"  # Set your service name here
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

@app.post("/next_api")
async def next_api(request: Request):
    print("Received headers:")
    for key, value in request.headers.items():
        print(f" - {key}: {value}")
        
    ctx = propagate.extract(request.headers)
    with trace.get_tracer(__name__).start_as_current_span("next_api_span", context=ctx):
        return {"message": "This is the next API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
