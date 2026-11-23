# M5Paper thin client

Firmware for the **original M5Paper v1.1** (ESP32, IT8951E, GT911, BM8563), not M5Paper S3. It shows whatever the [hub](../hub/README.md) sends and reports taps and the wheel. It has no knowledge of feeds, pages or layout, so new content never needs a flash.

## Configure, build, flash

```sh
cd device
cp include/secrets.h.example include/secrets.h     # Wi-Fi (2.4 GHz) and HUB_URL
uvx --from platformio pio run
uvx --from platformio pio run -t upload --upload-port /dev/ttyUSB0
```

`secrets.h` is git-ignored. Without it the build still works and the panel shows "Not configured".

## What it does

1. Wake (RTC alarm on battery, ESP32 timer on USB, or the wheel button).
2. Join Wi-Fi and `POST /device/sync` with the frame id it shows, the battery voltage and any input ([protocol](../hub/PROTOCOL.md)).
3. Inflate the rectangles that come back, load them into the panel, run one update over their bounding box.
4. On a scheduled wake, cut power for the time the hub asked for. On a manual wake, show `AWAKE` in the header, take input for the time the hub allows after the last input, then sleep.

Input is sent to the hub as is: a tap as coordinates, the wheel as `left`, `right`, `press` (short) or `hold` (1 s).

If the hub cannot be reached it tries once more, then writes `offline HH:MM` in the header strip, keeps the old picture and retries every 120 s. With no picture to keep it shows a full-screen message.

State in NVS (namespace `thin`): the frame id, and whether the status strip or a device message is showing. On battery the ESP32 keeps no RAM across the power cut.

## Test over USB

```sh
uvx --from pyserial python tools/serial_test.py r "t 545 510" h
```

This resets the board (a manual wake), prints its log, and sends input through the serial test hook: `l`, `r`, `p`, `h`, or `t X Y` for a tap. Each sync prints one line with the frame id, rectangle count, bytes and timings. Add `--no-reset --seconds 700` to watch scheduled wakes instead.

On USB the board cannot cut its own power, so it falls back to ESP32 deep sleep. Unplug to test the real battery path; hold the wheel for about two seconds to power up.

Measured on the LAN: Wi-Fi association about 1.8 s, a hub answer 50–300 ms, a full-screen frame 8–26 KB, a clean full refresh about 1.2 s, a partial update about 0.5 s.

## Files

| File | Role |
|---|---|
| `src/main.cpp` | Wake, sync, input loop, sleep |
| `src/net.cpp` | Wi-Fi, the sync request, parsing and inflating rectangles |
| `src/screen.cpp` | Panel writes, the status strip, the fallback message |
| `src/power.cpp` | Wake reason, RTC, power-off |
| `boards/m5stack-paper.json` | Board definition (Espressif32 does not register `m5stack-paper`) |

## Board and library notes

`boards/m5stack-paper.json` defines the board locally because Espressif32 6.13.0 does not register `m5stack-paper`. It selects 16 MB flash, the Arduino 16 MB partition table, and PSRAM. The build uses Espressif32 `^6.5.0` and M5EPD `0.1.5`; verified with Espressif32 6.13.0 (Arduino ESP32 2.0.17). M5EPD emits a non-fatal `ADC_ATTEN_DB_11` deprecation warning on a clean build.

M5EPD 0.1.5 uses **0°/180° for 960×540** and 90°/270° for 540×960. `WritePartGram4bpp()` sends `0xFFFF - word`, so ink level 0 is white and 15 is black; x and width must be multiples of four.

The BM8563's `M5.shutdown(seconds)` uses the countdown timer and latches **TF** (bit 2 of register `0x01`), not the alarm flag. The countdown has minute resolution above 255 s and tops out at 255 minutes.

The microSD slot shares SCK, MOSI and MISO with the panel. The firmware initialises the SD library even though it stores nothing there: an uninitialised card treats the pixel stream as SD commands, answers on the shared line, and the panel loses pixels (text sheared sideways from some row down).
