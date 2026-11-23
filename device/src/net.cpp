#include "net.h"

#include "power.h"
#include "screen.h"

#include <Arduino.h>
#include <HTTPClient.h>
#include <M5EPD.h>
#include <WiFi.h>
#include <esp32/rom/miniz.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#define WIFI_SSID ""
#define WIFI_PASS ""
#define HUB_URL ""
#endif

namespace {
constexpr uint32_t kWiFiTimeoutMs = 15000;
constexpr uint32_t kHttpTimeoutMs = 20000;  // Covers a feed action the hub runs before answering.
constexpr size_t kFrameBytes = kWidth * kHeight / 2;
constexpr int kMaxRects = 64;

bool connectWiFi() {
    if (WiFi.status() == WL_CONNECTED) return true;
    WiFi.persistent(false);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    const uint32_t started = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - started >= kWiFiTimeoutMs) {
            Serial.println("WiFi association timed out");
            return false;
        }
        delay(50);
    }
    Serial.printf("WiFi up in %lu ms, RSSI %d\n", static_cast<unsigned long>(millis() - started), WiFi.RSSI());
    return true;
}

bool readExact(WiFiClient &client, uint8_t *dest, size_t size, uint32_t deadline) {
    size_t got = 0;
    while (got < size) {
        if (static_cast<int32_t>(deadline - millis()) <= 0) return false;
        const int n = client.read(dest + got, size - got);
        if (n > 0) got += n;
        else if (!client.connected() && !client.available()) return false;
        else delay(1);
    }
    return true;
}

uint16_t u16(const uint8_t *p) { return p[0] | p[1] << 8; }
uint32_t u32(const uint8_t *p) { return u16(p) | static_cast<uint32_t>(u16(p + 2)) << 16; }

bool inflate(const uint8_t *in, size_t inSize, uint8_t *out, size_t outSize) {
    auto *state = static_cast<tinfl_decompressor *>(malloc(sizeof(tinfl_decompressor)));
    if (!state) return false;
    tinfl_init(state);
    size_t consumed = inSize, produced = outSize;
    const tinfl_status status = tinfl_decompress(
        state, in, &consumed, out, out, &produced,
        TINFL_FLAG_PARSE_ZLIB_HEADER | TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
    free(state);
    return status == TINFL_STATUS_DONE && produced == outSize;
}

// Reads the rectangles that follow the header and draws them.
bool drawRects(WiFiClient &client, int count, uint32_t deadline, SyncResult &result) {
    struct Area { int x, y, w, h; };
    int left = kWidth, top = kHeight, right = 0, bottom = 0;
    Mode mode = Mode::Quiet;
    for (int i = 0; i < count; ++i) {
        uint8_t head[16];
        if (!readExact(client, head, sizeof head, deadline)) return false;
        const Area a{u16(head), u16(head + 2), u16(head + 4), u16(head + 6)};
        const uint8_t encoding = head[9];
        const size_t length = u32(head + 12), pixels = static_cast<size_t>(a.w) * a.h / 2;
        if (a.w <= 0 || a.h <= 0 || a.x + a.w > kWidth || a.y + a.h > kHeight || a.x % 4 || a.w % 4 ||
            length == 0 || length > kFrameBytes + 1024 || encoding > 1 || (encoding == 0 && length != pixels)) {
            Serial.println("Bad rectangle from hub");
            return false;
        }
        auto *data = static_cast<uint8_t *>(ps_malloc(length));
        auto *raw = encoding == 1 ? static_cast<uint8_t *>(ps_malloc(pixels)) : data;
        bool ok = data && raw && readExact(client, data, length, deadline);
        if (ok && encoding == 1) ok = inflate(data, length, raw, pixels);
        if (ok) {
            result.panelTouched = true;
            ok = loadArea(a.x, a.y, a.w, a.h, raw);
        }
        if (raw != data) free(raw);
        free(data);
        if (!ok) {
            Serial.printf("Rectangle %d failed\n", i);
            return false;
        }
        if (i == 0) mode = static_cast<Mode>(head[8]);
        left = min(left, a.x), top = min(top, a.y);
        right = max(right, a.x + a.w), bottom = max(bottom, a.y + a.h);
    }
    // One waveform over the bounding box costs the same time as one small
    // area, and far less than one per rectangle.
    return count == 0 || showArea(left, top, right - left, bottom - top, mode);
}
}  // namespace

bool networkConfigured() {
    return WIFI_SSID[0] != '\0' && strncmp(HUB_URL, "http://", 7) == 0;
}

bool syncWithHub(uint32_t have, bool scheduled, const char *event, SyncResult &result) {
    result = {};
    if (!networkConfigured() || !connectWiFi()) return false;

    uint8_t mac[6];
    WiFi.macAddress(mac);
    char body[224];
    const int bodySize = snprintf(
        body, sizeof body, "{\"id\":\"m5-%02x%02x%02x\",\"have\":%lu,\"bat_mv\":%lu,\"wake\":\"%s\",\"fw\":%d%s%s}",
        mac[3], mac[4], mac[5], static_cast<unsigned long>(have),
        static_cast<unsigned long>(M5.getBatteryVoltage()), scheduled ? "timer" : "manual", kFirmwareVersion,
        event ? ",\"ev\":" : "", event ? event : "");
    if (bodySize <= 0 || bodySize >= static_cast<int>(sizeof body)) return false;

    WiFiClient client;
    HTTPClient http;
    http.setConnectTimeout(5000);
    http.setTimeout(kHttpTimeoutMs);
    http.useHTTP10(true);
    if (!http.begin(client, HUB_URL "/device/sync")) return false;
    http.addHeader("Content-Type", "application/json");
    const uint32_t started = millis();
    const int status = http.POST(reinterpret_cast<uint8_t *>(body), bodySize);
    const int length = http.getSize();
    const uint32_t deadline = started + kHttpTimeoutMs;
    uint8_t head[16];
    bool ok = status == HTTP_CODE_OK && length >= static_cast<int>(sizeof head) &&
              readExact(client, head, sizeof head, deadline) && memcmp(head, "M5H1", 4) == 0 &&
              head[11] <= kMaxRects;
    if (!ok) Serial.printf("Sync failed (HTTP %d, size %d)\n", status, length);
    const uint32_t answered = millis();
    if (ok) {
        ok = drawRects(client, head[11], deadline, result);
        result.rects = head[11];
    }
    http.end();
    if (!ok) return false;

    result.frameId = u32(head + 4);
    result.sleepSeconds = u16(head + 8);
    result.awakeSeconds = head[10];
    setClock(head[12], head[13], head[14]);
    Serial.printf("Sync ok: frame %08lx, %d rects, %d bytes, answer %lu ms, draw %lu ms, sleep %u s\n",
                  static_cast<unsigned long>(result.frameId), result.rects, length,
                  static_cast<unsigned long>(answered - started), static_cast<unsigned long>(millis() - answered),
                  result.sleepSeconds);
    return true;
}

void stopWiFi() {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
}
