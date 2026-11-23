#include "screen.h"

#include <M5EPD.h>

namespace {
m5epd_update_mode_t updateMode(Mode mode) {
    switch (mode) {
        case Mode::Clean: return UPDATE_MODE_GC16;
        case Mode::Fast: return UPDATE_MODE_DU4;
        default: return UPDATE_MODE_GL16;
    }
}
}  // namespace

bool loadArea(int x, int y, int w, int h, const uint8_t *pixels) {
    // M5EPD sends 16-bit words, so x and w must be multiples of four.
    if (x < 0 || y < 0 || w <= 0 || h <= 0 || x + w > kWidth || y + h > kHeight || x % 4 || w % 4) return false;
    return M5.EPD.WritePartGram4bpp(x, y, w, h, pixels) == M5EPD_OK;
}

bool showArea(int x, int y, int w, int h, Mode mode) {
    // CheckAFSR waits for the waveform, so power can be cut right after.
    return M5.EPD.UpdateArea(x, y, w, h, updateMode(mode)) == M5EPD_OK && M5.EPD.CheckAFSR() == M5EPD_OK;
}

bool drawStatus(const char *text) {
    M5EPD_Canvas canvas(&M5.EPD);
    const void *buffer = canvas.createCanvas(kStatusW, kStatusH);
    if (!buffer) return false;
    canvas.fillCanvas(M5EPD_Canvas::G0);
    canvas.setFreeFont(&FreeSansBold9pt7b);
    canvas.setTextColor(M5EPD_Canvas::G15);
    canvas.setTextDatum(MR_DATUM);
    canvas.drawString(text, kStatusW - 4, kStatusH / 2);
    const bool ok = loadArea(kStatusX, kStatusY, kStatusW, kStatusH, static_cast<const uint8_t *>(buffer)) &&
                    showArea(kStatusX, kStatusY, kStatusW, kStatusH, Mode::Fast);
    canvas.deleteCanvas();
    return ok;
}

bool drawMessage(const char *title, const char *detail) {
    M5EPD_Canvas canvas(&M5.EPD);
    const void *buffer = canvas.createCanvas(kWidth, kHeight);
    if (!buffer) return false;
    canvas.fillCanvas(M5EPD_Canvas::G0);
    canvas.setTextColor(M5EPD_Canvas::G15);
    canvas.setTextDatum(TL_DATUM);
    canvas.setFreeFont(&FreeSansBold24pt7b);
    canvas.drawString(title, 48, 150);
    canvas.setFreeFont(&FreeSans12pt7b);
    canvas.drawString(detail, 48, 240);
    const bool ok = loadArea(0, 0, kWidth, kHeight, static_cast<const uint8_t *>(buffer)) &&
                    showArea(0, 0, kWidth, kHeight, Mode::Clean);
    canvas.deleteCanvas();
    return ok;
}
