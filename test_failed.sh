#!/bin/bash

echo "=================================================="
echo "Sending FAILED task to Producer API"
echo "=================================================="

# Send failed message
echo -e "\n[Error Message] Sending request that will trigger error in Consumer..."
curl -X POST "http://localhost:38000/send_task_failed/" \
  -H "Content-Type: application/json" \
  -d '{"message": "This message will crash consumer"}' \
  -w "\nHTTP Status: %{http_code}\n"


echo -e "\n=================================================="
echo "Test complete! Check Consumer logs for error."
echo "=================================================="
echo "Please wait 10 seconds for traces to appear in Tempo"
sleep 10

echo -e "\nQuerying Tempo for recent traces..."
curl -s "http://localhost:33200/api/search?limit=5" | jq '.' || echo "Could not query Tempo"

echo -e "\nDONE! Go to Grafana and look for traces with RED error icon."
