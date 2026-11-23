#!/usr/bin/env python3
"""Strata usage feed: turns strata-usage's /api/eink snapshot into hub widgets.

Prints one feed (see ../hub/FEEDS.md) on stdout. The hub runs it as an `exec`
source and passes `--action` when a button is tapped:

    range:1h | range:24h   which range the totals and charts show (remembered)
    power:<watts>          POST /api/power-limit on strata-usage
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

POWER_LIMITS = (210, 240, 270, 300)  # Same choices as strata-usage's POWER_LIMITS.
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "m5paper-feeds/strata.json"


def compact(n):
    for limit, unit in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
        if n >= limit:
            return f"{n / limit:.3g}{unit}"
    return str(n)


def number(value, digits=1):
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "—"


def set_power(base, watts):
    request = urllib.request.Request(
        base + "/api/power-limit", data=json.dumps({"watts": watts}).encode(),
        headers={"Content-Type": "application/json", "X-Strata-Action": "power-limit",
                 "Sec-Fetch-Site": "same-origin"})
    urllib.request.urlopen(request, timeout=10).read()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default="http://127.0.0.1:8090/api/eink")
    parser.add_argument("--action")
    args = parser.parse_args()
    base = args.url.removesuffix("/api/eink")

    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {}
    kind, _, value = (args.action or "").partition(":")
    if kind == "range" and value in ("1h", "24h"):
        state["range"] = value
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state))
    elif kind == "power" and value.isdigit() and int(value) in POWER_LIMITS:
        set_power(base, int(value))
    elif args.action:
        sys.exit(f"unknown action {args.action!r}")
    chosen = state.get("range", "24h")

    with urllib.request.urlopen(args.url, timeout=10) as response:
        snap = json.load(response)
    data = snap["ranges"][chosen]
    totals, buckets = data["totals"], data["buckets"]
    per = "5 min" if chosen == "1h" else "hour"
    labels = [b["t"] for b in buckets]
    gpu = snap.get("gpu") or {}
    hit = f"{100 * totals['cache'] / totals['input']:.0f}% hit" if totals["input"] else "—"
    share = f"{100 * totals['output'] / totals['input']:.1f}% of input" if totals["input"] else "—"

    widgets = {
        "tok_s": {"type": "metric", "label": "TOK/S", "value": number(snap.get("tok_s_latest")),
                  "sub": f"avg {number(data.get('tok_s_avg'))} ({chosen})"},
        "input": {"type": "metric", "label": f"INPUT {chosen}", "value": compact(totals["input"]),
                  "sub": f"{totals['runs']:,} runs"},
        "cache": {"type": "metric", "label": f"CACHED {chosen}", "value": compact(totals["cache"]), "sub": hit},
        "output": {"type": "metric", "label": f"OUTPUT {chosen}", "value": compact(totals["output"]), "sub": share},
        "input_chart": {"type": "bars", "label": f"Input tokens / {per}", "x": labels,
                        "note": f"max {compact(max((b['input'] for b in buckets), default=0))}",
                        "series": [{"name": "cached", "values": [min(b["cache"], b["input"]) for b in buckets]},
                                   {"name": "new", "values": [max(b["input"] - b["cache"], 0) for b in buckets]}]},
        "output_chart": {"type": "bars", "label": f"Output tokens / {per}", "x": labels,
                         "note": f"max {compact(max((b['output'] for b in buckets), default=0))}",
                         "values": [b["output"] for b in buckets]},
        "range": {"type": "buttons", "label": "Range",
                  "options": [{"label": r, "action": f"range:{r}", "selected": r == chosen} for r in ("1h", "24h")]},
    }
    if isinstance(gpu.get("util_now"), (int, float)):
        widgets["gpu"] = {"type": "gauge", "label": "GPU", "value": gpu["util_now"], "max": 100,
                          "text": f"{gpu['util_now']}%",
                          "note": f"avg {gpu['util_avg']}%" if gpu.get("util_avg") is not None else ""}
    if gpu.get("vram_used_mib") is not None and gpu.get("vram_total_mib"):
        widgets["vram"] = {"type": "gauge", "label": "VRAM", "value": gpu["vram_used_mib"],
                           "max": gpu["vram_total_mib"],
                           "text": f"{gpu['vram_used_mib'] / 1024:.1f} / {gpu['vram_total_mib'] / 1024:.1f} GiB"}
    cap = snap.get("power_cap_w")
    if isinstance(cap, (int, float)):
        widgets["power"] = {"type": "buttons", "label": "Power limit W",
                            "options": [{"label": str(w), "action": f"power:{w}", "selected": w == cap}
                                        for w in POWER_LIMITS]}
    feed = {"v": 1, "title": "Strata", "ttl_s": 900, "widgets": widgets}
    if snap.get("stale"):
        feed["ttl_s"] = 1  # strata-usage itself says its data is old.
    json.dump(feed, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
