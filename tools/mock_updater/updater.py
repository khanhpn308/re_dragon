#!/usr/bin/env python3
"""
Lightweight Mock HTTP Updater for ReturnSaiyan Client (Port 30008)
Responds to /app.vm and /resource.vm update checks, confirming the client
is at the current version with zero required downloads.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="[UPDATER] %(asctime)s - %(message)s")

class UpdateHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        logging.info(f"Received request: {self.path}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {
            "needUpdate": False,
            "newestVersion": "1.0.17",
            "resVersion": "1.0.17",
            "code": 0,
            "status": "OK"
        }
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format, *args):
        logging.info("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))

def run(host="127.0.0.1", port=30008):
    server = HTTPServer((host, port), UpdateHandler)
    logging.info(f"Starting mock update server on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    logging.info("Update server stopped.")

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 30008
    run(port=port)
