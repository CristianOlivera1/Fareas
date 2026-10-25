#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <Adafruit_NeoPixel.h>

const char* WIFI_SSID = "OLIVERA";
const char* WIFI_PASS = "olivera#123";

const char* SERVER_HOST = "192.168.1.6";
const uint16_t SERVER_PORT = 8000;
const char* DEVICE_TOKEN = "63aab9309d64c79c340e90632c3ef1999cde1dbd89aecebcbbc3fb55d2826885";
const char* DEVICE_ID = "esp32-lab104";

const uint8_t RING_PIN = 13;
const uint8_t BUZZER_PIN = 26;
const uint16_t RING_LEDS = 16;
const uint8_t RING_BRIGHTNESS = 60;

const uint32_t HEARTBEAT_EVERY_MS = 30000;
const uint32_t RECONNECT_EVERY_MS = 5000;

Adafruit_NeoPixel ring(RING_LEDS, RING_PIN, NEO_GRB + NEO_KHZ800);
WebSocketsClient socket;

uint32_t lastHeartbeat = 0;
uint32_t showUntil = 0;
bool showing = false;

uint32_t colorFor(const char* name) {
  if (!strcmp(name, "verde")) return ring.Color(0, 180, 0);
  if (!strcmp(name, "amarillo")) return ring.Color(220, 140, 0);
  if (!strcmp(name, "rojo")) return ring.Color(200, 0, 0);
  if (!strcmp(name, "azul")) return ring.Color(0, 60, 200);
  return ring.Color(0, 0, 0);
}

void beep(uint8_t times, uint16_t durationMs) {
  for (uint8_t i = 0; i < times; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(durationMs);
    digitalWrite(BUZZER_PIN, LOW);
    if (i + 1 < times) delay(120);
  }
}

void playBuzzer(const char* pattern) {
  if (!strcmp(pattern, "beep_1")) beep(1, 150);
  else if (!strcmp(pattern, "beep_2")) beep(2, 150);
  else if (!strcmp(pattern, "tono_denegado")) beep(1, 700);
}

void showVerdict(const char* color, const char* buzzer, uint16_t seconds) {
  ring.fill(colorFor(color));
  ring.show();
  playBuzzer(buzzer);
  showing = true;
  showUntil = millis() + (uint32_t)seconds * 1000;
}

void clearRing() {
  ring.clear();
  ring.show();
  showing = false;
}

void sendHello() {
  String hello = String("{\"type\":\"hello\",\"device_id\":\"") + DEVICE_ID +
                 "\",\"mac\":\"" + WiFi.macAddress() + "\"}";
  socket.sendTXT(hello);
}

void onSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      Serial.println("[WS] conectado");
      sendHello();
      lastHeartbeat = millis();
      break;
    case WStype_DISCONNECTED:
      Serial.println("[WS] desconectado");
      break;
    case WStype_TEXT: {
      JsonDocument doc;
      if (deserializeJson(doc, payload, length)) return;
      const char* kind = doc["type"] | "";
      Serial.printf("[WS] %s\n", (const char*)payload);
      if (!strcmp(kind, "verdict")) {
        showVerdict(doc["color"] | "", doc["buzzer"] | "ninguno", doc["seconds"] | 3);
      }
      break;
    }
    default:
      break;
  }
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("[WiFi] conectando");
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  Serial.printf("\n[WiFi] IP %s\n", WiFi.localIP().toString().c_str());
}

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  ring.begin();
  ring.setBrightness(RING_BRIGHTNESS);
  clearRing();

  connectWifi();

  String path = String("/api/v1/ws/devices?token=") + DEVICE_TOKEN;
  socket.begin(SERVER_HOST, SERVER_PORT, path);
  socket.onEvent(onSocketEvent);
  socket.setReconnectInterval(RECONNECT_EVERY_MS);
}

void loop() {
  socket.loop();

  if (showing && (int32_t)(millis() - showUntil) >= 0) clearRing();

  if (socket.isConnected() && millis() - lastHeartbeat >= HEARTBEAT_EVERY_MS) {
    lastHeartbeat = millis();
    socket.sendTXT("{\"type\":\"heartbeat\"}");
  }
}
