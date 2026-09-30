import json
import logging
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import threading
from typing import Any, Callable, Dict, List, Optional
from database import db
from esp32_client import esp32_client

logger = logging.getLogger("AttendanceServer")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server capable of handling multiple concurrent requests."""
    daemon_threads = True
    allow_reuse_address = True


class AttendanceRequestHandler(BaseHTTPRequestHandler):
    """Exact-match HTTP Request Handler compliant with existing ESP32 firmware protocol."""

    # Event dispatchers set by the server instance
    on_punch_recorded: Optional[Callable[[Dict[str, Any]], None]] = None
    on_heartbeat_received: Optional[Callable[[Dict[str, Any]], None]] = None
    on_bulk_synced: Optional[Callable[[int, List[Dict[str, Any]]], None]] = None

    def log_message(self, format, *args):
        # Silence default stderr logging to keep console clean
        logger.debug("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), format % args))

    def _send_json_response(self, status_code: int, data: Dict[str, Any]):
        """Helper to send JSON response with standard headers."""
        try:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _validate_api_key(self) -> bool:
        """Validate incoming request header X-API-KEY."""
        configured_key = db.get_setting("api_key", "esp32_super_secure_token_98765")
        client_key = self.headers.get("X-API-KEY", "")
        return client_key == configured_key

    def do_OPTIONS(self):
        """Handle CORS pre-flight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-KEY")
        self.end_headers()

    def do_GET(self):
        """Simple health check endpoint for testing."""
        norm_path = self.path.rstrip("/")
        if norm_path == "/api/status" or norm_path == "":
            self._send_json_response(200, {
                "server": "SmartHR Desktop Biometric Server",
                "status": "online",
                "version": "5.0.0-SMART"
            })
        else:
            self._send_json_response(404, {"error": "not_found"})

    def do_POST(self):
        """Handle exact endpoints required by ESP32 firmware."""
        # 1. Check Security Header
        if not self._validate_api_key():
            self._send_json_response(401, {"error": "unauthorized"})
            return

        # 2. Parse Payload
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            self._send_json_response(400, {"error": "invalid_json"})
            return

        # Normalize path by removing trailing slash for resilient matching
        path = self.path.rstrip("/")

        # Endpoint 1: POST /api/attendance/heartbeat
        if path == "/api/attendance/heartbeat":
            self.handle_heartbeat(payload)

        # Endpoint 2: POST /api/attendance/punch
        elif path == "/api/attendance/punch":
            self.handle_punch(payload)

        # Endpoint 3: POST /api/attendance/bulk-punch
        elif path == "/api/attendance/bulk-punch":
            self.handle_bulk_punch(payload)

        else:
            self._send_json_response(404, {"error": "unknown_endpoint"})

    def handle_heartbeat(self, payload: Dict[str, Any]):
        """
        POST /api/attendance/heartbeat/
        Payload: {"device_name": "...", "ip": "...", "rssi": -55, "enrolled_count": 12, "firmware": "5.0.0-SMART"}
        Response: HTTP 200 {"status": "ok"}
        """
        # If IP was not included or is loopback, resolve from client socket
        if not payload.get("ip") or payload.get("ip") == "0.0.0.0":
            payload["ip"] = self.client_address[0]

        # Update telemetry in memory
        esp32_client.update_telemetry(payload)

        # Notify GUI subscriber
        if AttendanceRequestHandler.on_heartbeat_received:
            try:
                AttendanceRequestHandler.on_heartbeat_received(payload)
            except Exception as e:
                logger.error(f"Error in on_heartbeat_received callback: {e}")

        self._send_json_response(200, {"status": "ok"})

    def handle_punch(self, payload: Dict[str, Any]):
        """
        POST /api/attendance/punch/
        Payload: {"fingerprint_id": int, "device_id": "..."}
        Responses:
        - 404 {"error": "unlinked"}
        - 403 {"error": "inactive"}
        - 200 {"status": "ignored", "punch_type": "DEBOUNCED"}
        - 200 {"status": "success", "punch_type": "IN"}
        - 200 {"status": "success", "punch_type": "OUT"}
        """
        fingerprint_id = payload.get("fingerprint_id")
        device_id = payload.get("device_id", "ESP32_MAIN")

        if fingerprint_id is None:
            self._send_json_response(400, {"error": "missing_fingerprint_id"})
            return

        try:
            fid = int(fingerprint_id)
        except ValueError:
            self._send_json_response(400, {"error": "invalid_fingerprint_id"})
            return

        # Process via Database Manager
        success, punch_type, status_code, meta = db.process_punch(
            fingerprint_id=fid,
            device_id=device_id,
            is_offline_sync=0,
        )

        if not success:
            if status_code == 404:
                self._send_json_response(404, {"error": "unlinked"})
            elif status_code == 403:
                self._send_json_response(403, {"error": "inactive"})
            else:
                self._send_json_response(status_code, {"error": punch_type})
            return

        if punch_type == "DEBOUNCED":
            # Cooldown window active: respond with ignored
            self._send_json_response(200, {"status": "ignored", "punch_type": "DEBOUNCED"})
            return

        # Success check-in or check-out
        response_payload = {
            "status": "success",
            "punch_type": punch_type,  # "IN" or "OUT"
        }
        self._send_json_response(200, response_payload)

        # Notify UI and Telegram Bot
        if AttendanceRequestHandler.on_punch_recorded and meta:
            try:
                AttendanceRequestHandler.on_punch_recorded(meta)
            except Exception as e:
                logger.error(f"Error in on_punch_recorded callback: {e}")

    def handle_bulk_punch(self, payload: Dict[str, Any]):
        """
        POST /api/attendance/bulk-punch/
        Payload: {"punches": [{"fingerprint_id": int, "seconds_ago": int, "device_id": "..."}, ...]}
        Response: HTTP 200 {"status": "synced", "count": N}
        """
        punches = payload.get("punches", [])
        if not isinstance(punches, list):
            self._send_json_response(400, {"error": "punches_must_be_array"})
            return

        count, synced_records = db.process_bulk_punches(punches)

        if AttendanceRequestHandler.on_bulk_synced and count > 0:
            try:
                AttendanceRequestHandler.on_bulk_synced(count, synced_records)
            except Exception as e:
                logger.error(f"Error in on_bulk_synced callback: {e}")

        self._send_json_response(200, {"status": "synced", "count": count})


class AttendanceServer:
    """Wrapper to start, stop, and configure the embedded HTTP server in a background thread."""

    def __init__(self):
        self.server: Optional[ThreadedHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False

    def start(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        on_punch: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_heartbeat: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_bulk: Optional[Callable[[int, List[Dict[str, Any]]], None]] = None,
    ) -> bool:
        """Start the HTTP server on configured or specified host/port."""
        if self.is_running:
            return True

        h = host or db.get_setting("server_host", "0.0.0.0")
        p = int(port or db.get_setting("server_port", "8000"))

        AttendanceRequestHandler.on_punch_recorded = on_punch
        AttendanceRequestHandler.on_heartbeat_received = on_heartbeat
        AttendanceRequestHandler.on_bulk_synced = on_bulk

        try:
            self.server = ThreadedHTTPServer((h, p), AttendanceRequestHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self.is_running = True
            logger.info(f"Attendance HTTP Server listening on {h}:{p}")
            return True
        except Exception as e:
            logger.error(f"Failed to start Attendance HTTP Server on {h}:{p}: {e}")
            self.is_running = False
            return False

    def stop(self) -> None:
        """Gracefully stop the HTTP server."""
        if self.server and self.is_running:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception as e:
                logger.error(f"Error shutting down server: {e}")
            self.is_running = False
            logger.info("Attendance HTTP Server stopped.")

    def restart(self, host: Optional[str] = None, port: Optional[int] = None) -> bool:
        """Restart the server with new configuration."""
        self.stop()
        return self.start(host=host, port=port)


# Global shared server instance
attendance_server = AttendanceServer()
