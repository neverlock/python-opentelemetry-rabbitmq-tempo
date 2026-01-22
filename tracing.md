# Developer Guide: วิธีการเขียน Code สำหรับ Tracing (OpenTelemetry)

เอกสารนี้อธิบายวิธีการเขียนโค้ดเพื่อทำ Distributed Tracing ในระบบ Python ที่มีการสื่อสารผ่านทั้ง RabbitMQ และ HTTP โดยเน้นที่จุดสำคัญที่ Programmer ต้องรู้เพื่อให้ Trace เชื่อมต่อกันสมบูรณ์

## 1. การ Setup OpenTelemetry (Boilerplate)

ทุก Service ต้องมีการตั้งค่าพื้นฐานเหมือนกัน (ควรแยกเป็น Module กลางถ้าทำได้) เพื่อกำหนดว่า Service ชื่ออะไร และส่งข้อมูลไปที่ไหน

```python
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# 1. กำหนด Identity ของ Service
resource = Resource.create({
    SERVICE_NAME: "my-service-name",  # สำคัญ: ชื่อนี้จะไปโชว์ใน Grafana
    "service.namespace": "my-project",
})

# 2. Setup Provider และ Exporter
provider = TracerProvider(resource=resource)
# ส่งข้อมูลไปที่ Tempo (Port 4317 สำหรับ gRPC)
otlp_exporter = OTLPSpanExporter(endpoint="http://tempo:4317", insecure=True)
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)

# 3. กำหนด Propagator (ตัวกำหนด format ของ header ที่จะส่งข้าม service)
# B3MultiFormat นิยมใช้และรองรับ trace-id, span-id
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry import propagate
propagate.set_global_textmap(b3_format)
```

## 2. การส่ง Trace ผ่าน RabbitMQ (Manual Propagation)

RabbitMQ ไม่มี Standard HTTP Headers อัตโนมัติเหมือน HTTP เราจึงต้อง **Inject** (ฝัง) และ **Extract** (แกะ) Context เองผ่าน `properties.headers` ของ message

### ฝั่งผู้ส่ง (Producer) - การ Inject Context

```python
from opentelemetry import trace, propagate

tracer = trace.get_tracer(__name__)

# Start Span ใหม่
with tracer.start_as_current_span("send_to_queue", kind=SpanKind.PRODUCER) as span:
    
    # 1. เตรียม Dictionary ว่างๆ เพื่อรับ Trace Context
    headers = {}
    
    # 2. สั่ง Inject context ปัจจุบันลงใน headers dictionary
    # ผลลัพธ์จะได้ประมาณ: {'X-B3-TraceId': '...', 'X-B3-SpanId': '...'}
    propagate.inject(headers)
    
    # 3. ส่ง headers นี้ไปพร้อมกับ RabbitMQ Message properties
    channel.basic_publish(
        exchange='',
        routing_key='task_queue',
        body=json.dumps(data),
        properties=pika.BasicProperties(
            delivery_mode=2,
            headers=headers  # <--- จุดสำคัญ: แนบ Headers ไปที่นี่
        )
    )
```

### ฝั่งผู้รับ (Consumer) - การ Extract Context

```python
from opentelemetry import trace, propagate, context

def callback(ch, method, properties, body):
    # 1. อ่าน headers ที่แนบมากับ message
    headers = properties.headers or {}
    
    # 2. Extract context ออกมาเป็น Object
    ctx = propagate.extract(headers)
    
    # 3. Start Span ใหม่ โดยระบุว่า parent context คือ ctx ที่ extract มา
    # Trace ID เดิมจะถูกนำมาใช้ต่อ ทำให้กราฟเชื่อมกัน
    with tracer.start_as_current_span("process_message", context=ctx, kind=SpanKind.CONSUMER) as span:
        # ทำงาน logic ของ consumer ต่อในนี้
        process_data(body)
```

## 3. การส่ง Trace ผ่าน HTTP (Auto Instrumentation)

สำหรับการเรียก API ผ่าน HTTP (`requests library`) เราสามารถใช้ Library ช่วย Inject header อัตโนมัติได้ ไม่ต้องทำ manual เหมือน RabbitMQ

```python
# ที่หัวไฟล์ consumer
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# เรียกแค่ครั้งเดียวตอน start app
RequestsInstrumentor().instrument()

# ... ใน code ...
# เมื่อยิง request library จะ auto-inject header ให้เอง
requests.post("http://next-api/endpoint", json=data) 
# ^^^ Trace ID จะถูกส่งไปโดยอัตโนมัติ
```

## 4. Attributes ที่จำเป็นสำหรับ Service Graph (Node Graph)

เพื่อให้ Grafana วาดเส้นเชื่อมโยง (Node Graph) สวยๆ จำเป็นต้องใส่ Attributes พิเศษ เพื่อบอกความสัมพันธ์

**Producer Span:**
```python
span.set_attribute("peer.service", "consumer-service-name") # บอกปลายทาง
span.set_attribute("messaging.system", "rabbitmq")
span.set_attribute("messaging.destination", "queue_name")
```

**Consumer Span:**
```python
# Span Kind ต้องเป็น CONSUMER หรือ Client เพื่อให้รู้ว่าเป็นฝั่งรับหรือเรียกต่อ
# Consumer Logic
with tracer.start_as_current_span("...", kind=SpanKind.CONSUMER):
   ...

# HTTP Client call Logic
with tracer.start_as_current_span("call_api", kind=SpanKind.CLIENT):
   span.set_attribute("peer.service", "next-api-service") # บอกปลายทาง
```

## สรุปเช็คลิสต์สำหรับ Developer

1. [ ] **Setup**: มี Resource name ที่ถูกต้องและ Unique
2. [ ] **Cross-service**: 
   - RabbitMQ: ต้อง `inject` ก่อน send และ `extract` ตอน receive
   - HTTP: ใช้ Instrumentation library ช่วยเสมอ
3. [ ] **Linking**: ต้องใช้ `context=ctx` ตอน start span ฝั่งรับเสมอ ไม่งั้นจะได้ Trace ID ใหม่ (กราฟขาด)
4. [ ] **Graph**: ใส่ `peer.service` และ `SpanKind` ให้ถูกต้องเพื่อให้ Grafana วาด Map ได้
