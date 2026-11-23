#pragma once

#include <stdint.h>

constexpr int kFirmwareVersion = 1;

struct SyncResult {
    uint32_t frameId;   // What the panel now shows, as named by the hub.
    uint16_t sleepSeconds;
    uint8_t awakeSeconds;
    uint8_t rects;      // How many rectangles were redrawn.
    bool panelTouched;  // False if the request failed before any pixel changed.
};

bool networkConfigured();
// One round trip to the hub: report state (and an optional event, a JSON
// object such as {"key":"left"}), then draw whatever comes back.
bool syncWithHub(uint32_t have, bool scheduled, const char *event, SyncResult &result);
void stopWiFi();
