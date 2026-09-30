# ESP32 Biometric Hardware Setup & Flashing Guide

This firmware turns an ESP32 microcontroller into a smart network biometric terminal that connects directly to the **SmartHR Desktop Attendance System**.

---

### 1. Hardware Required
1. **ESP32 DevKit V1** (or ESP32-WROOM-32)
2. **Optical Fingerprint Sensor** (AS608 / R307 / FPM10A / DY50)
3. **5V Active Buzzer**
4. **Status LEDs** (1x Green for Success, 1x Red for Error / Unlinked)
5. Breadboard and Jumper Wires

---

### 2. Wiring Diagram

| Optical Sensor Pin | ESP32 DevKit Pin | Notes |
| :--- | :--- | :--- |
| **VCC (Red)** | 5V (VIN) | 3.3V or 5V depending on sensor module |
| **GND (Black)** | GND | Common ground |
| **TX (Yellow / Green)** | GPIO 16 (RX2) | Serial2 RX |
| **RX (White / Blue)** | GPIO 17 (TX2) | Serial2 TX |

| Peripheral | ESP32 Pin | Notes |
| :--- | :--- | :--- |
| **Green LED (Anode)** | GPIO 19 | via 220Ω resistor |
| **Red LED (Anode)** | GPIO 21 | via 220Ω resistor |
| **Active Buzzer (+)** | GPIO 18 | via 100Ω resistor or transistor |

---

### 3. Arduino IDE / PlatformIO Libraries
Install these libraries via Arduino Library Manager:
- `Adafruit Fingerprint Sensor Library` (by Adafruit)
- `ArduinoJson` (v6.x or v7.x by Benoit Blanchon)
- `WiFi` & `HTTPClient` & `WebServer` (included in official ESP32 Arduino Core)

---

### 4. Configuration
Open `esp32_attendance.ino` and update:
```cpp
const char* WIFI_SSID     = "YOUR_OFFICE_WIFI";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// IP address of the Desktop PC running SmartHR
const char* SERVER_HOST   = "192.168.1.100";  
const int   SERVER_PORT   = 8000;
const char* API_KEY       = "esp32_super_secure_token_98765";
```

---

### 5. Verified Endpoints & Flow
1. **Heartbeat**: Every 15 seconds, the ESP32 posts its signal strength (RSSI), IP address, and enrolled template count to:
   `POST /api/attendance/heartbeat/` with header `X-API-KEY`.
2. **Real-Time Punch**: When a finger matches an enrolled slot, it sends:
   `POST /api/attendance/punch/` with `{"fingerprint_id": ID, "device_id": "ESP32_MAIN"}`.
3. **Offline Punch Buffer**: If Wi-Fi is temporarily lost, punches are stored in memory with relative elapsed time and uploaded automatically via:
   `POST /api/attendance/bulk-punch/` as soon as connection is re-established.
4. **Desktop Remote Control**:
   - `POST http://<ESP32_IP>/enroll` with `slot=<id>` to start scanning from the PC.
   - `POST http://<ESP32_IP>/delete` with `slot=<id>` to delete template.
   - `POST http://<ESP32_IP>/test` to flash LEDs and beep buzzer.
