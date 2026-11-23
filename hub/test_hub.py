"""Run: uv run --no-project --with pillow --with pytest pytest hub/test_hub.py"""

import json
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import frame  # noqa: E402
import hub as hub_module  # noqa: E402
import render  # noqa: E402

FEED = {"v": 1, "title": "T", "widgets": {
    "m": {"type": "metric", "label": "Speed", "value": 12.5, "unit": "km/h", "sub": "ok", "trend": [1, 3, 2]},
    "b": {"type": "bars", "label": "Bars", "values": [1, 2, 3], "x": ["a", "b", "c"]},
    "l": {"type": "line", "label": "Line", "values": [3, 1, 2]},
    "g": {"type": "gauge", "label": "Gauge", "value": 3, "max": 4},
    "n": {"type": "list", "label": "News", "items": ["日本語の見出しを折り返す" * 4, {"text": "two", "sub": "12:00"}]},
    "t": {"type": "text", "text": "hello world"},
    "k": {"type": "buttons", "label": "Mode", "options": [
        {"label": "A", "action": "mode:a", "selected": True}, {"label": "B", "action": "mode:b"}]},
}}
CONFIG = """
[[page]]
title = "One"
grid = [4, 2]
cells = [
  { w = "demo.m", at = [0, 0] }, { w = "demo.b", at = [1, 0] }, { w = "demo.l", at = [2, 0] },
  { w = "demo.g", at = [3, 0] }, { w = "demo.n", at = [0, 1, 2, 1] }, { w = "demo.t", at = [2, 1] },
  { w = "demo.k", at = [3, 1] },
]
[[page]]
title = "Two"
cells = [ { w = "missing.widget", at = [0, 0] } ]
"""


@pytest.fixture
def hub():
    with tempfile.TemporaryDirectory() as folder:
        config = Path(folder) / "config.toml"
        config.write_text(CONFIG)
        instance = hub_module.Hub(config, Path(folder) / "state")
        instance.put_feed("demo", FEED)
        yield instance


def sync(hub, canvas, have, **extra):
    body = hub.sync({"id": "m5-test", "have": have, "bat_mv": 4000, "wake": "manual", **extra})
    header, canvas = frame.decode(body, canvas)
    assert frame.frame_id(canvas) == header["frame_id"], "device image must equal the hub's frame"
    return header, canvas


def test_pack_round_trip():
    levels = Image.frombytes("L", (8, 2), bytes(range(16)))
    packed = frame.pack(levels)
    assert packed == bytes([0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF])


@pytest.mark.parametrize("bad", [
    [], {"v": 2, "widgets": {"a": {"type": "text"}}}, {"v": 1, "widgets": {}},
    {"v": 1, "widgets": {"A.b": {"type": "text"}}}, {"v": 1, "widgets": {"a": {"type": "nope"}}},
    {"v": 1, "ttl_s": -1, "widgets": {"a": {"type": "text"}}},
])
def test_bad_feeds_are_rejected(bad):
    with pytest.raises(ValueError):
        hub_module.check_feed(bad)


def test_first_sync_is_full_then_nothing(hub):
    header, canvas = sync(hub, None, 0)
    assert [r[:5] for r in header["rects"]] == [(0, 0, 960, 540, frame.GC16)]
    again, _ = sync(hub, canvas, header["frame_id"])
    assert all(r[1] + r[3] <= render.HEADER for r in again["rects"])  # At most the clock changed.


def test_feed_change_sends_one_partial_rect(hub):
    header, canvas = sync(hub, None, 0)
    changed = json.loads(json.dumps(FEED))
    changed["widgets"]["g"]["value"] = 1
    hub.put_feed("demo", changed)
    header, canvas = sync(hub, canvas, header["frame_id"])
    (x, y, w, h, mode, _), = header["rects"]
    assert mode == frame.GL16 and x % 4 == 0 and w % 4 == 0 and w * h < 960 * 540 // 2


def test_unknown_frame_gets_everything(hub):
    header, canvas = sync(hub, None, 0)
    header, _ = sync(hub, None, 12345)
    assert header["rects"][0][2:4] == (960, 540)


def test_navigation_and_settings(hub):
    header, canvas = sync(hub, None, 0)
    header, canvas = sync(hub, canvas, header["frame_id"], ev={"key": "right"})
    assert hub.devices["m5-test"]["page"] == 1 and header["rects"][0][4] == frame.GC16
    header, canvas = sync(hub, canvas, header["frame_id"], ev={"tap": [20, 20]})  # header's left arrow
    assert hub.devices["m5-test"]["page"] == 0
    header, canvas = sync(hub, canvas, header["frame_id"], ev={"key": "hold"})
    assert hub.devices["m5-test"]["settings"]
    spot = next(s for s in hub.spots["m5-test"] if s[4] == "set:interval:120")
    header, canvas = sync(hub, canvas, header["frame_id"], ev={"tap": [spot[0] + 5, spot[1] + 5]})
    assert header["sleep_s"] == 120


def test_tap_on_a_stale_frame_is_ignored(hub):
    sync(hub, None, 0)
    sync(hub, None, 999, ev={"tap": [940, 20]})
    assert hub.devices["m5-test"]["page"] == 0


def test_feed_buttons_become_feed_actions(hub):
    sync(hub, None, 0)
    actions = [s[4] for s in hub.spots["m5-test"]]
    assert "feed:demo:mode:b" in actions and "feed:demo:mode:a" not in actions



def draw(widget, size=(240, 120)):
    img = Image.new("L", size, render.WHITE)
    render.WIDGETS[widget["type"]](render.ImageDraw.Draw(img), (0, 0, *size), widget)
    return img


def test_negative_bars_hang_below_the_zero_line():
    img = draw({"type": "bars", "values": [2, -2]})
    zero = (120 - 22) - (120 - 22 - 2) // 2  # the zero line sits halfway up the plot
    assert img.getpixel((60, zero - 20)) == render.BLACK and img.getpixel((60, zero + 20)) == render.WHITE
    assert img.getpixel((180, zero + 20)) == render.BLACK and img.getpixel((180, zero - 20)) == render.WHITE


def test_list_value_is_drawn_at_the_right_edge():
    plain = draw({"type": "list", "items": [{"text": "researcher"}]})
    valued = draw({"type": "list", "items": [{"text": "researcher", "value": 84}]})
    right = (200, 0, 240, 40)
    assert plain.crop(right).getextrema() == (render.WHITE, render.WHITE)
    assert valued.crop(right).getextrema()[0] == render.BLACK
    assert plain.crop((0, 0, 150, 120)).tobytes() == valued.crop((0, 0, 150, 120)).tobytes()
