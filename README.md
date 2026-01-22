# Python OpenTelemetry with RabbitMQ & Tempo Demo

โปรเจกต์นี้แสดงตัวอย่างการทำ Distributed Tracing ในระบบ Microservices ที่ใช้ Python และ RabbitMQ โดยส่งข้อมูล Traces ไปยัง Grafana Tempo และแสดงผลผ่าน Grafana Dashboard

## Architecture Overview

ระบบประกอบด้วย 3 Services หลัก:
1. **Producer**: รับ HTTP Request และส่งข้อความเข้า RabbitMQ (Inject trace context ลงใน headers)
2. **Consumer**: รับข้อความจาก RabbitMQ (Extract trace context) และเรียกไปที่ Next API
3. **Next API**: ปลายทางสุดท้ายที่รับ HTTP Request จาก Consumer

**Tracing Flow:**
`Client` → `Producer` → `RabbitMQ` → `Consumer` → `Next API`

## Prerequisites

- Docker และ Docker Compose

## วิธีการรันระบบ (How to run)

1. Clone repository และเข้าไปที่ folder โปรเจกต์
2. รันคำสั่ง Docker Compose เพื่อ start services ทั้งหมด:
   ```bash
   docker compose up -d --build
   ```
3. รอสักครู่ให้ services เริ่มทำงาน (ประมาณ 30 วินาที - 1 นาที) เพื่อให้ Tempo และ RabbitMQ พร้อมใช้งาน

## วิธีการทดสอบ (How to test)

เรามี script `test.sh` สำหรับยิง request ทดสอบให้:

1. รัน script ทดสอบ:
   ```bash
   chmod +x test.sh
   ./test.sh
   ```
   Script จะทำการยิง HTTP POST ไปที่ Producer จำนวน 3 ครั้ง และแสดง Trace ID กลับมา

2. หากต้องการยิง request เองด้วย curl:
   ```bash
   curl -X POST "http://localhost:8000/send_task/" \
     -H "Content-Type: application/json" \
     -d '{"message": "Hello Manual Test"}'
   ```

## การดูตวจสอบผลลัพธ์ (Verify Traces)

1. เปิด Browser ไปที่ **[http://localhost:3000](http://localhost:3000)** (Grafana)
2. ไปที่เมนู **Explore** (แถบซ้ายมือ รูปเข็มทิศ)
3. เลือก Datasource ด้านบนเป็น **Tempo**
4. ในส่วน QueryType เลือก **Search**
5. ที่ช่อง **Service Name** ให้เลือก `producer`
6. กดปุ่ม **Run query** มุมขวาบน
7. คลิกที่ Trace ID ที่ปรากฏขึ้นมาเพื่อดู Timeline
   - คุณควรเห็นกราฟที่แสดงการเชื่อมต่อจาก Producer -> Consumer -> Next API
8. คลิกแท็บ **Node Graph** เพื่อดูแผนภาพความสัมพันธ์ระหว่าง Services

## โครงสร้างการส่ง Trace Context

เพื่อให้ Tracing เชื่อมต่อกันได้สมบูรณ์ เราได้ทำดังนี้:

1. **Producer**: ใช้ `opentelemetry.propagate.inject` เพื่อใส่ `B3` headers (trace-id, span-id) ลงใน RabbitMQ message properties
2. **Consumer**: อ่าน headers จาก RabbitMQ message และใช้ `opentelemetry.propagate.extract` เพื่อสร้าง Span ที่ต่อเนื่องจาก Producer
3. **HTTP Client**: ใน Consumer เราใช้ `opentelemetry-instrumentation-requests` เพื่อส่ง Context ต่อไปยัง Next API โดยอัตโนมัติ

## Troubleshooting

หากไม่พบ Traces:
- ตรวจสอบว่า Container `tempo` รันอยู่และ healthy หรือไม่ (`docker compose ps`)
- ดู logs ของ services: `docker compose logs producer consumer`
- ตรวจสอบว่าพอร์ต 4317 (gRPC) และ 4318 (HTTP) ของ Tempo เปิดรับ connection (bind 0.0.0.0)

---
*Created for Tracing Demo*
