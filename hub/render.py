"""Draw pages of widgets as 960x540 grayscale images for the M5Paper.

Everything here is pure drawing: no network, no state. `render_page` returns
the image, the tap targets, and the rectangles that the hub diffs separately.
"""

from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 960, 540
HEADER = 44
# The device draws its own activity text here ("AWAKE", "offline 12:34").
# The hub must leave it white. Keep in sync with device/src/screen.h.
STATUS_RECT = (500, 6, 180, 32)

# Only the 16 levels the panel has, so nothing changes when quantising.
BLACK, DARK, MID, LIGHT, PALE, WHITE = 0x00, 0x44, 0x88, 0xBB, 0xDD, 0xFF
SERIES_INK = (BLACK, MID, LIGHT)
PAD = 12

FONT_DIRS = [
    Path(__file__).parent / "fonts",
    Path("/usr/share/fonts/opentype/noto"),
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/share/fonts/truetype/dejavu"),
]
FONT_FILES = {
    False: ["NotoSansCJK-Regular.ttc", "NotoSansCJKjp-Regular.otf", "DejaVuSans.ttf"],
    True: ["NotoSansCJK-Bold.ttc", "NotoSansCJKjp-Bold.otf", "DejaVuSans-Bold.ttf"],
}


@lru_cache(maxsize=None)
def font_path(bold):
    for name in FONT_FILES[bold]:
        for folder in FONT_DIRS:
            if (folder / name).exists():
                return str(folder / name)
    raise FileNotFoundError("no usable font; see hub/README.md (fonts)")


@lru_cache(maxsize=None)
def font(size, bold=False):
    return ImageFont.truetype(font_path(bold), size)


def text_width(text, size, bold=False):
    return font(size, bold).getlength(text)


def fit_size(text, width, sizes, bold=True):
    """The largest of `sizes` (descending) at which `text` fits `width`."""
    for size in sizes:
        if text_width(text, size, bold) <= width:
            return size
    return sizes[-1]


def ellipsize(text, width, size, bold=False):
    if text_width(text, size, bold) <= width:
        return text
    while text and text_width(text + "…", size, bold) > width:
        text = text[:-1]
    return text + "…"


def wrap(text, width, size, bold=False, max_lines=None):
    """Greedy wrap that breaks Latin text at spaces and CJK text anywhere."""
    tokens, word = [], ""
    for ch in " ".join(str(text).split()):
        if ch.isascii() and ch != " ":
            word += ch
            continue
        if word:
            tokens.append(word)
            word = ""
        tokens.append(ch)
    if word:
        tokens.append(word)

    lines, line = [], ""
    for token in tokens:
        if text_width(line + token, size, bold) <= width:
            line += token
            continue
        if line.strip():
            lines.append(line.rstrip())
        line = "" if token == " " else token
        while text_width(line, size, bold) > width:  # one word wider than the cell
            cut = len(line) - 1
            while cut > 1 and text_width(line[:cut], size, bold) > width:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
    if line.strip():
        lines.append(line.rstrip())
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = ellipsize(lines[-1] + "…", width, size, bold)
    return lines


def show(value):
    """Feeds may send numbers; show them without float noise."""
    if isinstance(value, bool) or value is None:
        return "—" if value is None else str(value)
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".") if abs(value) < 1000 else f"{value:,.0f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def compact(n):
    n = float(n)
    for limit, unit in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
        if abs(n) >= limit:
            return f"{n / limit:.3g}{unit}"
    return f"{n:.3g}"


def numbers(values):
    return [float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
            for v in (values if isinstance(values, list) else [])]


# --- widgets -----------------------------------------------------------------
# Each takes (draw, box, widget) where box = (x, y, w, h) is the area below the
# label row, and returns a list of tap targets (x, y, w, h, action).

def sparkline(d, box, values, ink=BLACK, width=2):
    x, y, w, h = box
    points = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(points) < 2 or w < 8 or h < 8:
        return None
    low, high = min(v for _, v in points), max(v for _, v in points)
    span = (high - low) or 1.0
    last = len(values) - 1
    line = [(x + i * (w - 1) / last, y + h - 1 - (v - low) / span * (h - 1)) for i, v in points]
    d.line(line, fill=ink, width=width, joint="curve")
    return low, high


def w_metric(d, box, widget):
    x, y, w, h = box
    value, unit = show(widget.get("value")), str(widget.get("unit") or "")
    sub = str(widget.get("sub") or "")
    trend = numbers(widget.get("trend"))
    sub_h = 26 if sub else 0
    trend_h = max(24, int(h * 0.3)) if len(trend) > 1 and h >= 110 else 0
    room = h - sub_h - trend_h
    sizes = [s for s in (96, 84, 72, 64, 56, 48, 40, 34, 28, 24, 20) if s * 1.15 <= room] or [20]
    unit_w = lambda s: text_width(" " + unit, max(16, s // 2), True) if unit else 0
    size = next((s for s in sizes if text_width(value, s, True) + unit_w(s) <= w), sizes[-1])
    base = y + (room + size * 0.74) / 2
    d.text((x, base), value, font=font(size, True), fill=BLACK, anchor="ls")
    if unit:
        d.text((x + text_width(value, size, True), base), " " + unit,
               font=font(max(16, size // 2), True), fill=DARK, anchor="ls")
    if sub:
        d.text((x, y + room + 20), ellipsize(sub, w, 20), font=font(20), fill=DARK, anchor="ls")
    if trend_h:
        sparkline(d, (x, y + h - trend_h + 4, w, trend_h - 6), trend)
    return []


def x_labels(d, x, y, w, labels, count, slots=True):
    """Draw as many of `labels` under a plot as fit without touching.

    Bars sit in `count` slots; line points run from edge to edge.
    """
    labels = [str(v) for v in labels] if isinstance(labels, list) else []
    if not labels or count < 1:
        return
    widest = max(text_width(v, 16) for v in labels) + 14
    step = 1
    while step < count and w / count * step < widest:
        step += 1
    for i in range(0, min(count, len(labels)), step):
        if labels[i]:
            cx = x + (i + 0.5) * w / count if slots else x + i * (w - 1) / max(count - 1, 1)
            cx = min(max(cx, x + text_width(labels[i], 16) / 2), x + w - text_width(labels[i], 16) / 2)
            d.text((cx, y), labels[i], font=font(16), fill=DARK, anchor="ma")


def series_of(widget):
    series = widget.get("series")
    if isinstance(series, list) and series:
        return [(str(s.get("name") or ""), numbers(s.get("values"))) for s in series if isinstance(s, dict)]
    return [("", numbers(widget.get("values")))]


def w_bars(d, box, widget):
    """Bars; several series are stacked, darkest nearest the zero line.

    Positive values stack upwards and negative ones downwards.
    """
    x, y, w, h = box
    series = series_of(widget)[:len(SERIES_INK)]
    count = max((len(v) for _, v in series), default=0)
    if not count:
        return []
    column = lambda i: [(v[i] or 0) for _, v in series if i < len(v)]
    high = max(max(sum(v for v in column(i) if v > 0) for i in range(count)), 0.0)
    low = min(min(sum(v for v in column(i) if v < 0) for i in range(count)), 0.0)
    span = (high - low) or 1.0
    plot_h = h - 22
    at = lambda v: y + plot_h - (v - low) / span * (plot_h - 2)
    d.line([(x, at(0)), (x + w, at(0))], fill=DARK)
    slot = w / count
    gap = 1 if slot < 8 else max(2, int(slot * 0.2))
    for i in range(count):
        left, right = x + i * slot + gap / 2, x + (i + 1) * slot - gap / 2
        up = down = 0.0
        for index, (_, values) in enumerate(series):
            v = (values[i] or 0) if i < len(values) else 0
            if v > 0:
                d.rectangle([left, at(up + v), right - 1, at(up)], fill=SERIES_INK[index])
                up += v
            elif v < 0:
                d.rectangle([left, at(down), right - 1, at(down + v)], fill=SERIES_INK[index])
                down += v
    x_labels(d, x, y + plot_h + 3, w, widget.get("x"), count)
    return []


def w_line(d, box, widget):
    x, y, w, h = box
    series = series_of(widget)[:len(SERIES_INK)]
    values = [v for _, vs in series for v in vs if v is not None]
    if len(values) < 2:
        return []
    low, high = min(values), max(values)
    fmt = (lambda v: show(round(v, 2))) if high < 1000 else (lambda v: f"{v:,.0f}")
    axis_w = int(max(text_width(fmt(low), 16), text_width(fmt(high), 16))) + 8
    plot = (x, y + 4, w - axis_w, h - 30)
    d.line([(x, y + 4 + plot[3]), (x + plot[2], y + 4 + plot[3])], fill=LIGHT)
    span = (high - low) or 1.0
    for index, (_, vs) in enumerate(series):
        last = max(len(vs) - 1, 1)
        points = [(plot[0] + i * (plot[2] - 1) / last, plot[1] + plot[3] - 1 - (v - low) / span * (plot[3] - 1))
                  for i, v in enumerate(vs) if v is not None]
        if len(points) > 1:
            d.line(points, fill=SERIES_INK[index], width=3 if index == 0 else 2, joint="curve")
    d.text((x + w, plot[1]), fmt(high), font=font(16), fill=DARK, anchor="ra")
    d.text((x + w, plot[1] + plot[3]), fmt(low), font=font(16), fill=DARK, anchor="rb")
    x_labels(d, x, y + h - 22, plot[2], widget.get("x"), max(len(vs) for _, vs in series), slots=False)
    return []


def w_gauge(d, box, widget):
    x, y, w, h = box
    value = widget.get("value")
    top = widget.get("max") or 100
    ratio = min(max(value / top, 0), 1) if isinstance(value, (int, float)) and top else 0
    text = str(widget.get("text") or (f"{ratio * 100:.0f}%" if isinstance(value, (int, float)) else "—"))
    bar_h = min(22, max(10, h // 4))
    size = fit_size(text, w, [s for s in (56, 48, 40, 34, 28, 24, 20) if s * 1.2 <= h - bar_h - 8] or [20])
    d.text((x, y + (h - bar_h - 8 + size * 0.74) / 2), text, font=font(size, True), fill=BLACK, anchor="ls")
    by = y + h - bar_h - 2
    d.rectangle([x, by, x + w - 1, by + bar_h], outline=BLACK, width=2)
    if ratio > 0:
        d.rectangle([x + 3, by + 3, x + 3 + (w - 7) * ratio, by + bar_h - 3], fill=DARK)
    return []


def w_list(d, box, widget):
    x, y, w, h = box
    size = int(widget.get("size") or 22)
    max_lines = int(widget.get("lines") or 2)
    line_h = int(size * 1.32)
    cy = y
    items = widget.get("items") if isinstance(widget.get("items"), list) else []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            item = {"text": item}
        sub = str(item.get("sub") or "")
        value = "" if item.get("value") is None else show(item["value"])
        room = max(w // 3, w - text_width(value, size) - 12) if value else w
        lines = wrap(item.get("text") or "", room, size, max_lines=max_lines)
        need = len(lines) * line_h + (20 if sub else 0)
        if cy + need > y + h:
            break
        if index:
            d.line([(x, cy - 5), (x + w, cy - 5)], fill=PALE)
        if value:
            d.text((x + w, cy), ellipsize(value, w - room - 12, size), font=font(size), fill=BLACK, anchor="ra")
        for line in lines:
            d.text((x, cy), line, font=font(size), fill=BLACK)
            cy += line_h
        if sub:
            d.text((x, cy - 2), ellipsize(sub, w, 16), font=font(16), fill=MID)
            cy += 20
        cy += 10
    return []


def w_text(d, box, widget):
    x, y, w, h = box
    size = int(widget.get("size") or 24)
    line_h = int(size * 1.35)
    lines = wrap(widget.get("text") or "", w, size, max_lines=max(1, h // line_h))
    for i, line in enumerate(lines):
        d.text((x, y + i * line_h), line, font=font(size), fill=BLACK)
    return []


def button(d, rect, label, selected=False, size=22):
    x, y, w, h = rect
    d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=8, fill=BLACK if selected else WHITE,
                        outline=BLACK, width=2)
    size = fit_size(label, w - 12, [s for s in (size, 20, 18, 16) if s <= size])
    d.text((x + w / 2, y + h / 2), ellipsize(label, w - 12, size, True), font=font(size, True),
           fill=WHITE if selected else BLACK, anchor="mm")


def w_buttons(d, box, widget):
    x, y, w, h = box
    options = [o for o in widget.get("options") or [] if isinstance(o, dict)]
    if not options:
        return []
    gap = 12 if len(options) < 4 else 8
    bw = (w - gap * (len(options) - 1)) // len(options)
    bh = min(h, 60)
    by = y + (h - bh) // 2
    spots = []
    for i, option in enumerate(options):
        rect = (x + i * (bw + gap), by, bw, bh)
        button(d, rect, str(option.get("label") or ""), bool(option.get("selected")))
        if option.get("action") and not option.get("selected"):
            spots.append((*rect, str(option["action"])))
    return spots


WIDGETS = {"metric": w_metric, "bars": w_bars, "line": w_line, "gauge": w_gauge,
           "list": w_list, "text": w_text, "buttons": w_buttons}


def draw_cell(d, rect, widget, label_override=None, stale=None):
    """One widget inside its grid cell, with the label row on top."""
    x, y, w, h = rect
    ix, iy, iw, ih = x + PAD, y + 8, w - 2 * PAD, h - 16
    if not isinstance(widget, dict) or widget.get("type") not in WIDGETS:
        d.text((ix, iy), ellipsize(label_override or "?", iw, 18, True), font=font(18, True), fill=DARK)
        d.text((ix, iy + 30), "no data", font=font(20), fill=MID)
        return []
    label = label_override if label_override is not None else str(widget.get("label") or "")
    note = f"stale {stale}" if stale else str(widget.get("note") or "")
    names = [name for name, _ in series_of(widget)] if widget["type"] in ("bars", "line") else []
    if label or note or any(names):
        right = ix + iw
        if note:
            d.text((right, iy + 2), note, font=font(16), fill=DARK, anchor="ra")
            right -= text_width(note, 16) + 12
        for index in reversed(range(len(names))):
            if names[index] and len(names) > 1:
                d.text((right, iy + 2), names[index], font=font(16), fill=DARK, anchor="ra")
                right -= text_width(names[index], 16) + 6
                d.rectangle([right - 12, iy + 7, right - 1, iy + 18], fill=SERIES_INK[index])
                right -= 24
        d.text((ix, iy), ellipsize(label, max(right - ix, 40), 18, True), font=font(18, True), fill=DARK)
        iy, ih = iy + 28, ih - 28
    spots = WIDGETS[widget["type"]](d, (ix, iy, iw, ih), widget)
    return [(sx - 6, sy - 6, sw + 12, sh + 12, action) for sx, sy, sw, sh, action in spots]


# --- page chrome -------------------------------------------------------------

def battery_percent(mv):
    """The board only reports mV; this is a coarse estimate, in 5% steps."""
    if not mv:
        return None
    return int(round((min(max(mv, 3300), 4200) - 3300) / 9 / 5) * 5)


def draw_header(d, title, index, total, now, battery_mv):
    """Header bar. Returns its tap targets."""
    d.line([(0, HEADER - 1), (W, HEADER - 1)], fill=BLACK, width=2)
    mid = HEADER // 2 - 1
    spots = []
    if total > 1:
        d.polygon([(30, mid - 10), (30, mid + 10), (16, mid)], fill=BLACK)
        d.polygon([(W - 30, mid - 10), (W - 30, mid + 10), (W - 16, mid)], fill=BLACK)
        spots += [(0, 0, 64, HEADER + 16, "nav:prev"), (W - 64, 0, 64, HEADER + 16, "nav:next")]
    d.text((56, mid), ellipsize(title, 380, 24, True), font=font(24, True), fill=BLACK, anchor="lm")
    if total > 1:
        x = 56 + min(text_width(title, 24, True), 380) + 18
        for i in range(total):
            box = [x + i * 16, mid - 4, x + i * 16 + 8, mid + 4]
            d.ellipse(box, fill=BLACK if i == index else None, outline=BLACK)

    d.text((W - 216, mid), now.strftime("%H:%M"), font=font(20), fill=DARK, anchor="rm")
    percent = battery_percent(battery_mv)
    bx = W - 204
    d.rectangle([bx, mid - 9, bx + 34, mid + 9], outline=BLACK, width=2)
    d.rectangle([bx + 35, mid - 4, bx + 38, mid + 4], fill=BLACK)
    if percent is not None:
        d.rectangle([bx + 4, mid - 5, bx + 4 + 26 * percent / 100, mid + 5], fill=BLACK)
        d.text((bx + 46, mid), f"{percent}%", font=font(18), fill=DARK, anchor="lm")
    # Menu icon: opens the hub's settings page.
    gx = W - 92
    for dy in (-7, 0, 7):
        d.line([(gx, mid + dy), (gx + 22, mid + dy)], fill=BLACK, width=3)
    spots.append((gx - 14, 0, 50, HEADER + 16, "nav:settings"))
    return spots


def cell_rect(grid, at):
    cols, rows = grid
    col, row, cs, rs = (list(at) + [1, 1])[:4]
    x0, x1 = W * col // cols, W * (col + cs) // cols
    body = H - HEADER
    y0, y1 = HEADER + body * row // rows, HEADER + body * (row + rs) // rows
    return x0, y0, x1 - x0, y1 - y0


def new_image():
    img = Image.new("L", (W, H), WHITE)
    return img, ImageDraw.Draw(img)


def render_page(page, lookup, index, total, now, battery_mv):
    """Draw one configured page.

    `lookup(ref)` returns (widget or None, stale "HH:MM" or None, feed name).
    Returns (image, tap targets, regions); regions are the rectangles whose
    content changes independently.
    """
    img, d = new_image()
    spots = draw_header(d, str(page.get("title") or ""), index, total, now, battery_mv)
    regions = [(0, 0, W, HEADER)]
    grid = page.get("grid") or [1, 1]
    for cell in page.get("cells") or []:
        rect = cell_rect(grid, cell.get("at") or [0, 0, 1, 1])
        x, y, w, h = rect
        if x + w < W:
            d.line([(x + w - 1, y + 10), (x + w - 1, y + h - 10)], fill=LIGHT)
        if y + h < H:
            d.line([(x + 10, y + h - 1), (x + w - 10, y + h - 1)], fill=LIGHT)
        widget, stale, feed = lookup(str(cell.get("w") or ""))
        extra = {k: v for k, v in cell.items() if k not in ("w", "at", "label")}
        if extra and isinstance(widget, dict):
            widget = {**widget, **extra}  # e.g. size = 20 for a list in a small cell
        for sx, sy, sw, sh, action in draw_cell(d, rect, widget, cell.get("label"), stale):
            spots.append((sx, sy, sw, sh, f"feed:{feed}:{action}"))
        regions.append(rect)
    return img, spots, regions


def render_settings(device, intervals, now, battery_mv, info):
    """The hub's own settings page."""
    img, d = new_image()
    spots = draw_header(d, "Settings", 0, 1, now, battery_mv)
    d.text((48, HEADER + 28), "Update interval", font=font(22, True), fill=DARK)
    gap, bw = 16, (W - 96 - 16 * (len(intervals) - 1)) // len(intervals)
    for i, seconds in enumerate(intervals):
        rect = (48 + i * (bw + gap), HEADER + 66, bw, 64)
        label = f"{seconds // 60} min" if seconds < 3600 else f"{seconds // 3600} h"
        selected = seconds == device.get("interval")
        button(d, rect, label, selected, 26)
        if not selected:
            spots.append((*rect, f"set:interval:{seconds}"))
    y = HEADER + 170
    for line in info:
        d.text((48, y), ellipsize(line, W - 96, 20), font=font(20), fill=DARK)
        y += 30
    done = (W - 48 - 200, H - 48 - 64, 200, 64)
    button(d, done, "Done", True, 26)
    spots.append((*done, "set:close"))
    full = (48, H - 48 - 64, 260, 64)
    button(d, full, "Clean screen", False, 24)
    spots.append((*full, "set:full"))
    return img, spots, [(0, 0, W, HEADER), (0, HEADER, W, H - HEADER)]


def render_message(title, detail, now, battery_mv):
    img, d = new_image()
    draw_header(d, "M5Paper hub", 0, 1, now, battery_mv)
    d.text((48, 150), title, font=font(40, True), fill=BLACK)
    for i, line in enumerate(wrap(detail, W - 96, 24)):
        d.text((48, 230 + i * 34), line, font=font(24), fill=DARK)
    return img, [], [(0, 0, W, HEADER), (0, HEADER, W, H - HEADER)]


def stale_time(received_at, ttl_s, now):
    """"HH:MM" of the last update if the feed has outlived its ttl."""
    if received_at is None or ttl_s is None:
        return None
    if now.timestamp() - received_at <= ttl_s:
        return None
    return datetime.fromtimestamp(received_at, now.tzinfo).strftime("%H:%M")
