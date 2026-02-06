#!/bin/bash

echo "=================================================="
echo "Sending test messages to Producer API"
echo "=================================================="

# Send first message
echo -e "\n[Message 1] Sending..."
curl -X POST "http://localhost:38000/send_task/" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello from test script - Message 1"}' \
  -w "\nHTTP Status: %{http_code}\n"

sleep 3

# Send second message
echo -e "\n[Message 2] Sending..."
curl -X POST "http://localhost:38000/send_task/" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello from test script - Message 2"}' \
  -w "\nHTTP Status: %{http_code}\n"

sleep 3

# Send third message
echo -e "\n[Message 3] Sending..."
curl -X POST "http://localhost:38000/send_task/" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello from test script - Message 3"}' \
  -w "\nHTTP Status: %{http_code}\n"

echo -e "\n=================================================="
echo "Test complete! Waiting for traces to be exported..."
echo "=================================================="
echo "Please wait 10 seconds for traces to appear in Tempo"
echo "Then open http://localhost:33000 to view traces in Grafana"
sleep 10

echo -e "\nQuerying Tempo for recent traces..."
curl -s "http://localhost:33200/api/search?limit=10" | jq '.' || echo "Could not query Tempo (jq may not be installed)"

echo -e "\nDone! You can now:"
echo "1. Open Grafana at http://localhost:33000"
echo "2. Go to Explore → Select 'Tempo' datasource"
echo "3. Search for service='producer' to see traces"
echo "4. Click on a trace to view the full trace timeline"
echo "5. Click on 'Node graph' tab to see the service graph"
