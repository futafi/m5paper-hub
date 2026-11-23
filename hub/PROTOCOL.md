# Device protocol

The device knows nothing about feeds or pages. It asks the hub what to draw, draws it, and reports input.

## Request

`POST /device/sync`, JSON, HTTP/1.0:

```json
{"id": "m5-a1b2c3", "have": 3549952766, "bat_mv": 4102, "wake": "timer", "fw": 1, "ev": {"tap": [545, 510]}}
```

| Field | Meaning |
|---|---|
| `id` | `m5-` plus the last three bytes of the MAC. Per-device state on the hub (page, interval) hangs off this. |
| `have` | The frame id the panel shows, or `0` if unknown. The device stores it in NVS only after a complete draw. |
| `wake` | `timer` for a scheduled wake, `manual` otherwise. Only timer wakes trigger the periodic clean refresh. |
| `ev` | Optional input: `{"tap": [x, y]}` or `{"key": "left" | "right" | "press" | "hold"}`. |

The hub resolves taps against the tap targets of frame `have`. A tap on any other frame is ignored. Keys map to previous page, next page, refresh this page's feeds, and settings.

## Response

Binary, little endian. A 16-byte header:

| Offset | Type | Field |
|---|---|---|
| 0 | 4 bytes | `"M5H1"` |
| 4 | u32 | frame id: CRC-32 of the full 960×540 ink-level image, never 0 |
| 8 | u16 | seconds to sleep before the next scheduled sync |
| 10 | u8 | seconds to stay awake after a manual wake or an input |
| 11 | u8 | number of rectangles (at most 64) |
| 12 | u8 ×3 | hub local time: hour, minute, second (sets the RTC for the `offline HH:MM` text) |
| 15 | u8 | flags, 0 |

Then each rectangle: a 16-byte header and its data.

| Offset | Type | Field |
|---|---|---|
| 0 | u16 ×4 | x, y, w, h. x and w are multiples of 4. |
| 8 | u8 | update mode: 0 GC16 (clean, flashes), 1 GL16 (quiet), 2 DU4 (fast). The first rectangle's mode is used for all. |
| 9 | u8 | encoding: 0 raw, 1 zlib |
| 10 | u16 | reserved |
| 12 | u32 | data length |

Pixels are 4 bits each, 15 = black, rows top to bottom, left pixel in the high nibble: `w * h / 2` bytes once decoded.

The device loads every rectangle into the panel's memory, then runs one update over their bounding box. Zero rectangles means the panel is already right.

The hub currently sends at most one rectangle: the box around everything that changed. That way the panel only ever displays pixels it was just given; after a power cut the controller's memory outside the loaded area cannot be trusted.

## Rules that keep the two sides in step

- The hub answers with a difference only if `have` equals the frame it last sent to that device. Otherwise it sends the whole screen with GC16.
- The hub also sends the whole screen when the page or the config changes, when "Clean screen" is tapped, and on a timer wake once `full_every_s` has passed since the last clean refresh with partial updates in between.
- If drawing fails part-way, the device sets `have` to 0.
- The strip `STATUS_RECT` (`hub/render.py`, `device/src/screen.h`) belongs to the device. The hub keeps it white; the device shows `AWAKE` or `offline HH:MM` there and clears it itself.
