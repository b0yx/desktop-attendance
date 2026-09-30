import json
import logging
import threading
from typing import Any, Dict, Optional, Tuple
import requests
from database import db

logger = logging.getLogger("ESP32Client")


class ESP32Client:
    """Manages outgoing control requests and hardware telemetry for the ESP32 biometric device."""

    def __init__(self):
        self._telemetry: Dict[str, Any] = {
            "device_name": "Unknown",
            "ip": "Offline",
            "rssi": None,
            "enrolled_count": 0,
            "firmware": "N/A",
            "last_seen": None,
            "is_online": False,
        }
        self._lock = threading.Lock()

    def get_base_url(self) -> str:
        ip = db.get_setting("esp32_ip", "192.168.1.50")
        port = db.get_setting("esp32_port", "80")
        return f"http://{ip}:{port}"

    def update_telemetry(self, data: Dict[str, Any]) -> None:
        """Update live telemetry received from heartbeat."""
        from datetime import datetime
        with self._lock:
            self._telemetry.update({
                "device_name": data.get("device_name", "ESP32-Biometric"),
                "ip": data.get("ip", "Unknown"),
                "rssi": data.get("rssi"),
                "enrolled_count": data.get("enrolled_count", 0),
                "firmware": data.get("firmware", "5.0.0-SMART"),
                "last_seen": datetime.now(),
                "is_online": True,
            })

    def get_telemetry(self) -> Dict[str, Any]:
        """Return a copy of the current hardware telemetry and online status."""
        from datetime import datetime, timedelta
        with self._lock:
            state = dict(self._telemetry)
            if state["last_seen"]:
                # If no heartbeat within 45 seconds, mark offline
                if datetime.now() - state["last_seen"] > timedelta(seconds=45):
                    state["is_online"] = False
            else:
                state["is_online"] = False
            return state

    def trigger_enrollment(self, slot_id: int, timeout: int = 25) -> Tuple[bool, str]:
        """
        Trigger enrollment procedure on ESP32 for the specified fingerprint slot:
        POST http://<ESP32_IP>/enroll with form data 'slot=<id>'
        """
        url = f"{self.get_base_url()}/enroll"
        try:
            response = requests.post(url, data={"slot": str(slot_id)}, timeout=timeout)
            if response.status_code == 200:
                return True, response.text or f"Enrollment successfully initiated for slot #{slot_id}."
            else:
                return False, f"Device returned status {response.status_code}: {response.text}"
        except requests.exceptions.Timeout:
            return False, "Request timed out. Please ensure the user placed their finger on the sensor in time."
        except requests.exceptions.ConnectionError:
            return False, f"Could not connect to ESP32 at {self.get_base_url()}. Verify device is powered and connected to LAN."
        except Exception as e:
            return False, f"Error triggering enrollment: {str(e)}"

    def delete_fingerprint(self, slot_id: int, timeout: int = 8) -> Tuple[bool, str]:
        """
        Delete fingerprint from ESP32 memory:
        POST http://<ESP32_IP>/delete with form data 'slot=<id>'
        """
        url = f"{self.get_base_url()}/delete"
        try:
            response = requests.post(url, data={"slot": str(slot_id)}, timeout=timeout)
            if response.status_code == 200:
                return True, f"Fingerprint slot #{slot_id} removed from device."
            else:
                return False, f"Device returned status {response.status_code}: {response.text}"
        except Exception as e:
            return False, f"Failed to delete fingerprint: {str(e)}"

    def test_hardware(self, timeout: int = 5) -> Tuple[bool, str]:
        """
        Trigger audio/visual hardware test on ESP32:
        POST http://<ESP32_IP>/test
        """
        url = f"{self.get_base_url()}/test"
        try:
            response = requests.post(url, timeout=timeout)
            if response.status_code == 200:
                return True, "Test command sent successfully. Buzzer & LED activated on device."
            else:
                return False, f"Device returned status {response.status_code}: {response.text}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"


# Global shared instance
esp32_client = ESP32Client()
