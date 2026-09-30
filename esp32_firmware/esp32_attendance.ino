/*
  ESP32 Production Biometric Attendance Firmware
  Compatible with SmartHR Desktop Attendance Management System
  Hardware: ESP32 DevKit V1 + Optical Fingerprint Sensor (R307/FPM10A/DY50) + Buzzer + Status LEDs
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <Adafruit_Fingerprint.h>

// ================= USER CONFIGURATION =================
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Desktop Application Server Settings
const char* SERVER_HOST   = "192.168.1.100";  // Desktop PC IP running SmartHR
const int   SERVER_PORT   = 8000;
const char* API_KEY       = "esp32_super_secure_token_98765";

// Hardware Pinout
#define FINGERPRINT_RX_PIN 16 // Connect to Sensor TX
#define FINGERPRINT_TX_PIN 17 // Connect to Sensor RX
#define BUZZER_PIN         18
#define LED_GREEN_PIN      19
#define LED_RED_PIN        21

// ================= GLOBALS & INSTANCES =================
HardwareSerial mySerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&mySerial);
WebServer server(80);

unsigned long lastHeartbeat = 0;
const unsigned long HEARTBEAT_INTERVAL = 15000; // Send heartbeat every 15s

// Offline Punch Buffer Structure
struct OfflinePunch {
  int fingerprint_id;
  unsigned long recorded_millis;
};
#define MAX_OFFLINE_BUFFER 50
OfflinePunch offlineBuffer[MAX_OFFLINE_BUFFER];
int offlineCount = 0;

// ================= HARDWARE SIGNALS =================
void beep(int ms, int count = 1) {
  for (int i = 0; i < count; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(ms);
    digitalWrite(BUZZER_PIN, LOW);
    if (i < count - 1) delay(80);
  }
}

void signalSuccess() {
  digitalWrite(LED_GREEN_PIN, HIGH);
  beep(120, 2);
  digitalWrite(LED_GREEN_PIN, LOW);
}

void signalError() {
  digitalWrite(LED_RED_PIN, HIGH);
  beep(300, 1);
  digitalWrite(LED_RED_PIN, LOW);
}

void signalDebounce() {
  digitalWrite(LED_GREEN_PIN, HIGH);
  digitalWrite(LED_RED_PIN, HIGH);
  beep(50, 1);
  delay(100);
  digitalWrite(LED_GREEN_PIN, LOW);
  digitalWrite(LED_RED_PIN, LOW);
}

// ================= HTTP SERVER ENDPOINTS =================
void handleRoot() {
  server.send(200, "text/plain", "ESP32 Smart Attendance Terminal Online");
}

void handleTest() {
  Serial.println("[REMOTE] Testing buzzer and LEDs...");
  digitalWrite(LED_GREEN_PIN, HIGH);
  digitalWrite(LED_RED_PIN, HIGH);
  beep(150, 3);
  digitalWrite(LED_GREEN_PIN, LOW);
  digitalWrite(LED_RED_PIN, LOW);
  server.send(200, "text/plain", "Hardware test passed");
}

void handleEnroll() {
  if (!server.hasArg("slot")) {
    server.send(400, "text/plain", "Missing 'slot' parameter");
    return;
  }
  int slot = server.arg("slot").toInt();
  if (slot < 1 || slot > 127) {
    server.send(400, "text/plain", "Slot must be between 1 and 127");
    return;
  }

  Serial.printf("[ENROLL] Starting enrollment for slot #%d...\n", slot);
  server.send(200, "text/plain", "Place finger on sensor now...");
  
  // Fast enrollment routine
  int p = -1;
  unsigned long timeout = millis() + 10000;
  while (p != FINGERPRINT_OK && millis() < timeout) {
    p = finger.getImage();
    delay(100);
  }
  if (p != FINGERPRINT_OK) {
    signalError();
    return;
  }

  p = finger.image2Tz(1);
  if (p != FINGERPRINT_OK) { signalError(); return; }
  beep(100);

  delay(1500); // Wait for finger release and second tap
  timeout = millis() + 10000;
  p = -1;
  while (p != FINGERPRINT_OK && millis() < timeout) {
    p = finger.getImage();
    delay(100);
  }
  if (p != FINGERPRINT_OK) { signalError(); return; }

  p = finger.image2Tz(2);
  if (p != FINGERPRINT_OK) { signalError(); return; }

  p = finger.createModel();
  if (p != FINGERPRINT_OK) { signalError(); return; }

  p = finger.storeModel(slot);
  if (p == FINGERPRINT_OK) {
    Serial.printf("[ENROLL] Successfully stored slot #%d!\n", slot);
    signalSuccess();
  } else {
    signalError();
  }
}

void handleDelete() {
  if (!server.hasArg("slot")) {
    server.send(400, "text/plain", "Missing slot parameter");
    return;
  }
  int slot = server.arg("slot").toInt();
  uint8_t p = finger.deleteModel(slot);
  if (p == FINGERPRINT_OK) {
    Serial.printf("[DELETE] Deleted slot #%d\n", slot);
    server.send(200, "text/plain", "Deleted");
    signalSuccess();
  } else {
    server.send(500, "text/plain", "Failed to delete from sensor");
    signalError();
  }
}

// ================= BACKEND CLIENT ACTIONS =================
void sendHeartbeat() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String("http://") + SERVER_HOST + ":" + SERVER_PORT + "/api/attendance/heartbeat/";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-KEY", API_KEY);

  finger.getTemplateCount();
  StaticJsonDocument<200> doc;
  doc["device_name"] = "ESP32-Biometric-Entrance";
  doc["ip"] = WiFi.localIP().toString();
  doc["rssi"] = WiFi.RSSI();
  doc["enrolled_count"] = finger.templateCount;
  doc["firmware"] = "5.0.0-SMART";

  String requestBody;
  serializeJson(doc, requestBody);

  int httpCode = http.POST(requestBody);
  if (httpCode == 200) {
    // Heartbeat OK
  }
  http.end();
}

void flushBulkBuffer() {
  if (offlineCount == 0 || WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String("http://") + SERVER_HOST + ":" + SERVER_PORT + "/api/attendance/bulk-punch/";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-KEY", API_KEY);

  DynamicJsonDocument doc(4096);
  JsonArray punches = doc.createNestedArray("punches");

  unsigned long currentMillis = millis();
  for (int i = 0; i < offlineCount; i++) {
    JsonObject p = punches.createNestedObject();
    p["fingerprint_id"] = offlineBuffer[i].fingerprint_id;
    p["seconds_ago"] = (currentMillis - offlineBuffer[i].recorded_millis) / 1000;
    p["device_id"] = "ESP32_MAIN";
  }

  String requestBody;
  serializeJson(doc, requestBody);

  int httpCode = http.POST(requestBody);
  if (httpCode == 200) {
    Serial.printf("[SYNC] Successfully uploaded %d offline punches!\n", offlineCount);
    offlineCount = 0; // Clear buffer
  }
  http.end();
}

void sendPunch(int fingerprint_id) {
  if (WiFi.status() != WL_CONNECTED) {
    // Buffer offline
    if (offlineCount < MAX_OFFLINE_BUFFER) {
      offlineBuffer[offlineCount].fingerprint_id = fingerprint_id;
      offlineBuffer[offlineCount].recorded_millis = millis();
      offlineCount++;
      Serial.printf("[OFFLINE] Buffered punch ID %d (total: %d)\n", fingerprint_id, offlineCount);
      signalSuccess();
    }
    return;
  }

  HTTPClient http;
  String url = String("http://") + SERVER_HOST + ":" + SERVER_PORT + "/api/attendance/punch/";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-KEY", API_KEY);

  StaticJsonDocument<200> doc;
  doc["fingerprint_id"] = fingerprint_id;
  doc["device_id"] = "ESP32_MAIN";

  String requestBody;
  serializeJson(doc, requestBody);

  int httpCode = http.POST(requestBody);
  String response = http.getString();
  http.end();

  Serial.printf("[PUNCH] Code: %d, Response: %s\n", httpCode, response.c_str());

  if (httpCode == 200) {
    StaticJsonDocument<200> respDoc;
    deserializeJson(respDoc, response);
    String status = respDoc["status"] | "";
    String pType = respDoc["punch_type"] | "";

    if (pType == "DEBOUNCED" || status == "ignored") {
      signalDebounce();
    } else {
      signalSuccess();
    }
  } else {
    signalError();
  }
}

// ================= SETUP & LOOP =================
void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_RED_PIN, OUTPUT);

  // Initialize Optical Fingerprint Sensor
  finger.begin(57600);
  if (finger.verifyPassword()) {
    Serial.println("Fingerprint sensor detected!");
  } else {
    Serial.println("Did not find fingerprint sensor :(");
  }

  // Connect to Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());
    beep(100, 2);
  }

  // Configure Web Server
  server.on("/", handleRoot);
  server.on("/test", HTTP_POST, handleTest);
  server.on("/enroll", HTTP_POST, handleEnroll);
  server.on("/delete", HTTP_POST, handleDelete);
  server.begin();
  Serial.println("HTTP Remote Server listening on port 80");
}

void loop() {
  server.handleClient();

  // Send periodic heartbeat
  if (millis() - lastHeartbeat > HEARTBEAT_INTERVAL) {
    lastHeartbeat = millis();
    sendHeartbeat();
    flushBulkBuffer();
  }

  // Check for finger on sensor
  uint8_t p = finger.getImage();
  if (p == FINGERPRINT_OK) {
    p = finger.image2Tz();
    if (p == FINGERPRINT_OK) {
      p = finger.fingerSearch();
      if (p == FINGERPRINT_OK) {
        Serial.printf("Found ID #%d with confidence %d\n", finger.fingerID, finger.confidence);
        sendPunch(finger.fingerID);
        delay(1500); // Sensor debounce delay
      } else {
        Serial.println("Finger not matched in database");
        signalError();
        delay(1000);
      }
    }
  }
  delay(50);
}
