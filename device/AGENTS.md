# Notes for agents working on the device firmware

Read `README.md` and `../hub/PROTOCOL.md` first.

- **Keep it thin.** Anything about content, layout, pages or settings belongs in the hub. Change the firmware only for hardware behaviour or the protocol.
- **Protocol and `kStatus*` are shared with the hub** (`../hub/frame.py`, `STATUS_RECT` in `../hub/render.py`). Change both sides together and bump `kFirmwareVersion` in `src/net.h`.
- **You cannot see the panel.** Verify with `tools/serial_test.py` (log and injected input) and the hub's `/device/<id>/frame.png`. Ask the user to look when appearance matters (ghosting, contrast).
- **Flashing is safe to repeat**; the M5Paper shows up as a CP2104 serial port, usually `/dev/ttyUSB0`.
- M5EPD 0.1.5: rotation 0 is 960×540. `WritePartGram4bpp` needs x and width in multiples of 4, and 15 is black. `CheckAFSR` waits for the waveform; call it before cutting power (`showArea` does).
- **Keep the SD card initialised** (`M5.begin(true, true, ...)`). The microSD slot shares SCK/MOSI/MISO with the panel; an uninitialised card answers the pixel stream as if it were SD commands and the panel loses words (text sheared sideways from some row down; seen 2026-11-23). The device's pixel data was correct by CRC and HRDY never dropped, so look at the bus first if it returns.
- `M5.RTC.begin()` clears the wake flags, so `scheduledWake()` must run before it.
- Inflate uses miniz from the ESP32 ROM (`esp32/rom/miniz.h`); buffers come from PSRAM (`ps_malloc`).
- `include/secrets.h` holds Wi-Fi credentials. Never print or commit it.
