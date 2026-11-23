#pragma once

#include <stddef.h>
#include <stdint.h>

constexpr int kWidth = 960, kHeight = 540;

// The hub leaves this strip of the header white for the device's own text.
// Keep in sync with STATUS_RECT in hub/render.py.
constexpr int kStatusX = 500, kStatusY = 6, kStatusW = 180, kStatusH = 32;

// Update modes as sent by the hub (hub/frame.py).
enum class Mode : uint8_t { Clean = 0, Quiet = 1, Fast = 2 };

// Write 4bpp pixels (15 = black, left pixel in the high nibble) to the panel's
// memory. Nothing is visible until showArea().
bool loadArea(int x, int y, int w, int h, const uint8_t *pixels);
bool showArea(int x, int y, int w, int h, Mode mode);

// Small text in the status strip; an empty string clears it.
bool drawStatus(const char *text);
// Full-screen text for when there is no frame from the hub to keep.
bool drawMessage(const char *title, const char *detail);
