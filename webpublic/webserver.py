from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime


class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """<!DOCTYPE html>
<html>
<head><title>Simple Web Server</title></head>
<body>
    <h1>Hello from Python Web Server!</h1>
    <p>Server is running.</p>
    <p>Try <a href="/api/health">/api/health</a> for health check.</p>
</body>
</html>"""
            self.wfile.write(html.encode())

        elif self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
            }
            self.wfile.write(json.dumps(data).encode())

        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode())


if __name__ == "__main__":
    port = 8888
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    print(f"Server running on http://0.0.0.0:{port}")
    server.serve_forever()
