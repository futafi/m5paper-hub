"""Turn rendered images into what the device draws: 4bpp rectangles.

Wire format of a sync response (little endian), see PROTOCOL.md:

    "M5H1" | frame_id u32 | sleep_s u16 | awake_s u8 | n_rects u8
           | hour u8 | minute u8 | second u8 | flags u8
    then n_rects times:
    x u16 | y u16 | w u16 | h u16 | mode u8 | encoding u8 | reserved u16
           | length u32 | data[length]
"""

import struct
import zlib

from PIL import Image, ImageChops

MAGIC = b"M5H1"
GC16, GL16, DU4 = 0, 1, 2  # Update modes: full flash, quiet grayscale, fast 4-level.
RAW, ZLIB = 0, 1
_SHIFT = bytes((v << 4) & 0xFF for v in range(256))
# 8-bit gray -> ink level 0 (white) .. 15 (black), as M5EPD expects.
_INK = [15 - (v >> 4) for v in range(256)]


def quantize(img):
    """Image of ink levels 0..15. All comparisons happen in this form."""
    return img.convert("L").point(_INK)


def pack(levels):
    """Ink-level image -> 4bpp rows, left pixel in the high nibble."""
    w, h = levels.size
    assert w % 2 == 0
    data = levels.tobytes()
    high, low = data[0::2].translate(_SHIFT), data[1::2]
    n = len(low)
    return (int.from_bytes(high, "big") | int.from_bytes(low, "big")).to_bytes(n, "big")


def frame_id(levels):
    """Identifies exactly what is on the panel. 0 is reserved for 'unknown'."""
    return zlib.crc32(levels.tobytes()) or 1


def changed_rects(old, new, regions):
    """One rectangle around everything that changed, or [] if nothing did.

    The device shows exactly the pixels it was sent. Sending several small
    rectangles and updating the box around them would make the controller
    display memory it was never given after a power cut. Looking region by
    region only keeps the comparison cheap.
    """
    left, top, right, bottom = new.width, new.height, 0, 0
    for x, y, w, h in regions:
        box = (x, y, x + w, y + h)
        diff = ImageChops.difference(old.crop(box), new.crop(box)).getbbox()
        if diff:
            left, top = min(left, x + diff[0]), min(top, y + diff[1])
            right, bottom = max(right, x + diff[2]), max(bottom, y + diff[3])
    if right <= left:
        return []
    left = left // 4 * 4  # The controller takes four pixels per word.
    right = min((right + 3) // 4 * 4, new.width)
    return [(left, top, right - left, bottom - top)]


def encode_rect(levels, rect, mode):
    x, y, w, h = rect
    raw = pack(levels.crop((x, y, x + w, y + h)))
    packed = zlib.compress(raw, 9)
    encoding, data = (ZLIB, packed) if len(packed) < len(raw) else (RAW, raw)
    return struct.pack("<HHHHBBHI", x, y, w, h, mode, encoding, 0, len(data)) + data


def encode(levels, rects, mode, sleep_s, awake_s, now):
    """A complete sync response. `rects` may be empty: nothing to draw."""
    body = struct.pack("<4sIHBBBBBB", MAGIC, frame_id(levels), min(sleep_s, 0xFFFF), min(awake_s, 255),
                       len(rects), now.hour, now.minute, now.second, 0)
    return body + b"".join(encode_rect(levels, rect, mode) for rect in rects)


def decode(body, canvas=None):
    """Inverse of `encode`, for tests and the simulator. Returns (header, canvas)."""
    magic, fid, sleep_s, awake_s, count, hour, minute, second, _ = struct.unpack_from("<4sIHBBBBBB", body)
    assert magic == MAGIC
    canvas = canvas.copy() if canvas else Image.new("L", (960, 540), 0)
    offset, rects = 16, []
    for _ in range(count):
        x, y, w, h, mode, encoding, _, length = struct.unpack_from("<HHHHBBHI", body, offset)
        offset += 16
        data = body[offset:offset + length]
        offset += length
        raw = zlib.decompress(data) if encoding == ZLIB else data
        assert len(raw) == w * h // 2 and x % 4 == 0 and w % 4 == 0
        pixels = bytearray(w * h)
        pixels[0::2] = bytes(b >> 4 for b in raw)
        pixels[1::2] = bytes(b & 15 for b in raw)
        canvas.paste(Image.frombytes("L", (w, h), bytes(pixels)), (x, y))
        rects.append((x, y, w, h, mode, length))
    assert offset == len(body)
    header = dict(frame_id=fid, sleep_s=sleep_s, awake_s=awake_s, time=(hour, minute, second), rects=rects)
    return header, canvas


def to_png_image(levels):
    """Ink levels back to a viewable grayscale image."""
    return levels.point([255 - v * 17 if v < 16 else 0 for v in range(256)])
