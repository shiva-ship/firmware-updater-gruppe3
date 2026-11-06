"""Local HTTP server that behaves like the IMPACT67 for driver tests. No real device is touched."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USERNAME = "test-user"
PASSWORD = "test-password"


class FakeImpact67:
    def __init__(self, firmware="V1.7.1", new_firmware="V1.9.1", product_id="298", hardware="V2.0.0"):
        self.firmware = firmware
        self.new_firmware = new_firmware
        self.product_id = product_id
        self.hardware = hardware
        self.upload_status = 200
        self.reset_status = 200
        self.drop_upload = False
        self.drop_reset = False
        self.identification_status = 200
        self.flash_on_failed_reset = False
        self.fail_reads = set()
        self.read_count = 0
        self.flaky_reads = 0
        self.offline = False
        self.offline_reads_after_reset = 2
        self.never_returns = False
        self.flash_changes_version = True
        self.login_calls = 0
        self.upload_calls = 0
        self.reset_calls = 0
        self.uploaded = None
        self.pending = False
        self.server = None

    def __enter__(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _authorized(self):
                expected = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
                return self.headers.get("Authorization") == f"Basic {expected}"

            def _send(self, status, body=b"{}"):
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _drop(self):
                self.close_connection = True
                self.connection.close()

            def do_GET(self):
                if self.path == "/iolink/v1/gateway/identification":
                    if fake.identification_status != 200:
                        return self._send(fake.identification_status)
                    fake.read_count += 1
                    if fake.read_count in fake.fail_reads:
                        return self._drop()
                    if fake.offline:
                        fake.offline_reads_after_reset -= 1
                        if fake.never_returns or fake.offline_reads_after_reset >= 0:
                            return self._drop()
                        fake.offline = False
                    if fake.flaky_reads > 0:
                        fake.flaky_reads -= 1
                        return self._drop()
                    body = {
                        "macAddress": "00:00:00:00:00:01",
                        "serialNumber": "TEST-SERIAL-1",
                        "productId": fake.product_id,
                        "vendorName": "Murrelektronik",
                        "productName": "IMPACT67 Pro PN DIO8 IOL8",
                        "hardwareRevision": fake.hardware,
                        "firmwareRevision": fake.firmware,
                    }
                    return self._send(200, json.dumps(body).encode())
                if self.path == "/netx/login":
                    fake.login_calls += 1
                    return self._send(200 if self._authorized() else 401)
                self._send(404)

            def do_POST(self):
                if not self._authorized():
                    return self._send(401)
                if self.path == "/netx/firmware":
                    fake.upload_calls += 1
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length)
                    if fake.drop_upload:
                        return self._drop()
                    if fake.upload_status == 200:
                        fake.uploaded = body
                        fake.pending = True
                    return self._send(fake.upload_status)
                if self.path == "/netx/reset":
                    fake.reset_calls += 1
                    if fake.drop_reset:
                        self._drop()
                    else:
                        self._send(fake.reset_status)
                    if (fake.reset_status == 200 or fake.flash_on_failed_reset) and fake.pending:
                        if fake.flash_changes_version:
                            fake.firmware = fake.new_firmware
                        fake.pending = False
                        fake.offline = True
                    return None
                self._send(404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"
