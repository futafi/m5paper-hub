// M5Paper thin client: shows what the hub sends, reports taps and the wheel.
// All content, layout and actions live in the hub (../hub).

#include "net.h"
#include "power.h"
#include "screen.h"

#include <M5EPD.h>
#include <Preferences.h>

namespace {
constexpr uint32_t kRetrySeconds = 120, kDefaultSleepSeconds = 600;
constexpr uint32_t kHoldMs = 1000;

Preferences prefs;
bool nvsReady;
uint32_t frameId;        // 0: the panel does not show a known hub frame.
bool statusShown;        // The status strip has text that must be cleared.
bool messageShown;       // A device-drawn full-screen message is up.
uint32_t sleepSeconds = kRetrySeconds, awakeMs = 15000;
uint32_t lastInteraction, centerPressedAt;
bool centerArmed, centerTracking, touching;
char serialLine[32];  // One serial test command.
uint8_t serialSize;

void setFrameId(uint32_t id) {
    if (id == frameId) return;
    frameId = id;
    if (nvsReady) prefs.putUInt("frame", id);
}

void setStatus(const char *text) {
    const bool show = text[0] != '\0';
    if (!show && !statusShown) return;
    if (!drawStatus(text)) Serial.println("Status strip update failed");
    if (show != statusShown) {
        statusShown = show;
        if (nvsReady) prefs.putBool("status", show);
    }
}

void setMessage(const char *title, const char *detail) {
    if (messageShown && frameId == 0) return;  // Already up; do not flash again.
    if (drawMessage(title, detail)) {
        setFrameId(0);
        messageShown = true;
        statusShown = false;
        if (nvsReady) {
            prefs.putBool("message", true);
            prefs.putBool("status", false);
        }
    }
}

// Talk to the hub once. `awake` keeps the "AWAKE" marker up afterwards.
bool sync(bool scheduled, const char *event, bool awake) {
    if (!networkConfigured()) {
        setMessage("Not configured", "Set WIFI_SSID, WIFI_PASS and HUB_URL in include/secrets.h.");
        return false;
    }
    SyncResult result;
    bool ok = false;
    for (int attempt = 0; attempt < 2 && !ok; ++attempt) {
        if (attempt) delay(2000);
        ok = syncWithHub(frameId, scheduled, attempt ? nullptr : event, result);
        if (!ok && result.panelTouched) setFrameId(0);  // Partly drawn: ask for everything next time.
    }
    if (!ok) {
        sleepSeconds = kRetrySeconds;
        if (frameId == 0 && !result.panelTouched) {
            setMessage("Hub unavailable", "Check Wi-Fi and the hub. Retrying automatically.");
        } else {
            char text[20], time[6];
            clockText(time);
            snprintf(text, sizeof text, "offline %s", time);
            setStatus(text);
        }
        return false;
    }
    if (messageShown) {
        messageShown = false;
        if (nvsReady) prefs.putBool("message", false);
    }
    setFrameId(result.frameId);
    sleepSeconds = result.sleepSeconds ? result.sleepSeconds : kDefaultSleepSeconds;
    awakeMs = max<uint32_t>(result.awakeSeconds, 5) * 1000;
    // A full-screen answer already wiped the strip; otherwise clear stale text.
    setStatus(awake ? "AWAKE" : "");
    return true;
}

[[noreturn]] void sleepNow() {
    if (statusShown && frameId != 0) setStatus("");
    sleepFor(sleepSeconds);
}

void sendEvent(const char *event) {
    sync(false, event, true);
    lastInteraction = millis();
}

// Test hook: the same events over the serial port, one per line:
//   l | r | p | h          wheel left / right / press / hold
//   t <x> <y>              tap
void serialCommand(const char *line) {
    int x, y;
    char event[40];
    if (!strcmp(line, "l")) sendEvent("{\"key\":\"left\"}");
    else if (!strcmp(line, "r")) sendEvent("{\"key\":\"right\"}");
    else if (!strcmp(line, "p")) sendEvent("{\"key\":\"press\"}");
    else if (!strcmp(line, "h")) sendEvent("{\"key\":\"hold\"}");
    else if (sscanf(line, "t %d %d", &x, &y) == 2) {
        snprintf(event, sizeof event, "{\"tap\":[%d,%d]}", x, y);
        sendEvent(event);
    }
}
}  // namespace

void setup() {
    // The microSD slot shares SCK/MOSI/MISO with the panel. A card that is
    // never initialised stays in SD-bus mode, reads the panel's pixel stream as
    // commands and answers on the shared line, which makes the panel controller
    // lose words (text sheared a few pixels sideways). Initialising the SD
    // library puts the card in SPI mode, where it ignores the bus unless its
    // chip select (GPIO4) is low.
    M5.begin(true, true, true, true, false);
    pinMode(4, OUTPUT);
    digitalWrite(4, HIGH);
    // In M5EPD 0.1.5, 0 and 180 are 960x540; 90 is 540x960.
    M5.EPD.SetRotation(0);
    M5.TP.SetRotation(0);
    const bool scheduled = scheduledWake();
    M5.RTC.begin();

    nvsReady = prefs.begin("thin", false);
    if (nvsReady) {
        frameId = prefs.getUInt("frame", 0);
        statusShown = prefs.getBool("status", false);
        messageShown = prefs.getBool("message", false);
    }

    sync(scheduled, nullptr, !scheduled);
    if (scheduled) sleepNow();

    // Ignore the release of the long press that originally powered the board.
    M5.update();
    centerArmed = M5.BtnP.isReleased();
    lastInteraction = millis();
}

void loop() {
    M5.update();

    if (M5.BtnL.wasPressed()) sendEvent("{\"key\":\"left\"}");
    if (M5.BtnR.wasPressed()) sendEvent("{\"key\":\"right\"}");

    if (M5.TP.available()) {
        M5.TP.update();
        if (M5.TP.isFingerUp()) {
            touching = false;
        } else if (!touching && M5.TP.getFingerNum()) {
            touching = true;
            const auto touch = M5.TP.readFinger(0);
            char event[40];
            snprintf(event, sizeof event, "{\"tap\":[%d,%d]}", touch.x, touch.y);
            sendEvent(event);
        }
    }

    if (M5.BtnP.wasPressed()) {
        centerTracking = centerArmed;
        centerPressedAt = millis();
        lastInteraction = millis();
    }
    if (centerTracking && millis() - centerPressedAt >= kHoldMs) {
        centerTracking = false;
        sendEvent("{\"key\":\"hold\"}");
    }
    if (M5.BtnP.wasReleased()) {
        if (centerTracking) sendEvent("{\"key\":\"press\"}");
        centerArmed = true;
        centerTracking = false;
    }

    while (Serial.available()) {
        const char c = Serial.read();
        if (c == '\n' || c == '\r') {
            serialLine[serialSize] = '\0';
            if (serialSize) serialCommand(serialLine);
            serialSize = 0;
        } else if (serialSize < sizeof serialLine - 1) {
            serialLine[serialSize++] = c;
        }
    }

    if (millis() - lastInteraction >= awakeMs) sleepNow();
    delay(15);
}
