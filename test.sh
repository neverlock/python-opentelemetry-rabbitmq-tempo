#!/bin/bash
curl -X POST "http://localhost:8000/send_task/" -H "Content-Type: application/json" -d "{\"message\": \"Hello, World\"}"

