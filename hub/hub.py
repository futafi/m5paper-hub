#!/usr/bin/env python3
"""M5Paper hub: collects feeds, renders pages, and serves frames to the device.

    python3 hub.py --config config.toml --state ~/.local/state/m5paper-hub

See README.md (operation), FEEDS.md (feed format) and PROTOCOL.md (device).
"""

import argparse
import html
import io
import json
import re
import subprocess
import threading
import time
import tomllib
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

import frame
import render

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MAX_FEED_BYTES = 256 * 1024
DEFAULTS = dict(port=60091, bind="0.0.0.0", timezone="Asia/Tokyo", interval_s=600,
                intervals_s=[120, 300, 600, 1800], full_every_s=3600, awake_s=15,
                settings_awake_s=60, token="")
WEEKDAYS = "月火水木金土日"


def check_feed(data):
    """Raise ValueError unless `data` is a v1 feed. Returns it trimmed to known keys."""
    if not isinstance(data, dict) or data.get("v") != 1:
        raise ValueError('feed must be a JSON object with "v": 1')
    widgets = data.get("widgets")
    if not isinstance(widgets, dict) or not widgets:
        raise ValueError('"widgets" must be a non-empty object')
    for key, widget in widgets.items():
        if not NAME.match(key):
            raise ValueError(f"bad widget id {key!r}: use a-z, 0-9, _ and -")
        if not isinstance(widget, dict) or widget.get("type") not in render.WIDGETS:
            raise ValueError(f"widget {key!r}: type must be one of {sorted(render.WIDGETS)}")
    ttl = data.get("ttl_s")
    if ttl is not None and not (isinstance(ttl, (int, float)) and ttl > 0):
        raise ValueError('"ttl_s" must be a positive number')
    return {"v": 1, "title": str(data.get("title") or ""), "ttl_s": ttl, "widgets": widgets}


class Hub:
    def __init__(self, config_path, state_dir):
        self.config_path = Path(config_path).resolve()
        self.state = Path(state_dir).expanduser()
        (self.state / "feeds").mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.config, self.config_mtime, self.config_error = dict(DEFAULTS), 0, None
        self.feeds = {}      # name -> {"data": feed, "at": unix time, "error": str or None}
        self.running = {}    # name -> True while its source is being fetched
        self.next_run = {}
        self.frames = {}     # device id -> ink-level image the device shows
        self.spots = {}      # device id -> tap targets of that frame
        self.devices = {}
        self.load_config()
        for path in (self.state / "feeds").glob("*.json"):
            try:
                saved = json.loads(path.read_text())
                self.feeds[path.stem] = {"data": check_feed(saved["data"]), "at": saved["at"], "error": None}
            except (ValueError, KeyError, OSError):
                pass
        try:
            self.devices = json.loads((self.state / "devices.json").read_text())
        except (ValueError, OSError):
            pass

    # --- configuration -------------------------------------------------------

    def load_config(self):
        """(Re)read the config file if it changed. A broken file keeps the old config."""
        try:
            mtime = self.config_path.stat().st_mtime
            if mtime == self.config_mtime:
                return
            self.config_mtime = mtime
            loaded = tomllib.loads(self.config_path.read_text())
            for name in loaded.get("feed", {}):
                if not NAME.match(name):
                    raise ValueError(f"bad feed name {name!r}")
            self.config = {**DEFAULTS, **loaded}
            self.config_error = None
            self.next_run = {}
        except (OSError, ValueError) as error:
            self.config_error = str(error)
            print(f"config: {error}", flush=True)

    @property
    def pages(self):
        return [p for p in self.config.get("page", []) if isinstance(p, dict)]

    @property
    def sources(self):
        return {n: s for n, s in self.config.get("feed", {}).items() if s.get("exec") or s.get("url")}

    def now(self):
        return datetime.now(ZoneInfo(self.config["timezone"]))

    # --- feeds ---------------------------------------------------------------

    def put_feed(self, name, data):
        feed = check_feed(data)
        with self.lock:
            self.feeds[name] = {"data": feed, "at": time.time(), "error": None}
            saved = json.dumps({"data": feed, "at": self.feeds[name]["at"]}, ensure_ascii=False)
        (self.state / "feeds" / f"{name}.json").write_text(saved)

    def fetch(self, name, action=None):
        """Run a configured source once. Returns an error string or None."""
        source = self.sources.get(name)
        if not source:
            return "feed has no source for actions; use exec or url in the hub config"
        timeout = source.get("timeout_s", 20)
        try:
            if source.get("exec"):
                command = [str(part) for part in source["exec"]] + (["--action", action] if action else [])
                done = subprocess.run(command, cwd=self.config_path.parent, capture_output=True, timeout=timeout)
                if done.returncode:
                    raise ValueError(f"exit {done.returncode}: {done.stderr.decode(errors='replace')[-300:].strip()}")
                body = done.stdout
            else:
                payload = json.dumps({"action": action}).encode() if action else None
                request = urllib.request.Request(source["url"], data=payload,
                                                 headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    body = response.read(MAX_FEED_BYTES + 1)
            if len(body) > MAX_FEED_BYTES:
                raise ValueError("feed too large")
            self.put_feed(name, json.loads(body))
            return None
        except Exception as error:  # A feed must never take the hub down.
            message = f"{type(error).__name__}: {error}"
            print(f"feed {name}: {message}", flush=True)
            with self.lock:
                self.feeds.setdefault(name, {"data": None, "at": None})["error"] = message
            return message

    def fetch_async(self, name):
        with self.lock:
            if self.running.get(name):
                return None
            self.running[name] = True

        def work():
            try:
                self.fetch(name)
            finally:
                self.running[name] = False
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        return thread

    def schedule_forever(self):
        while True:
            self.load_config()
            now = time.time()
            for name, source in self.sources.items():
                if now >= self.next_run.get(name, 0):
                    self.next_run[name] = now + max(5, source.get("every_s", 300))
                    self.fetch_async(name)
            time.sleep(1)

    def ttl(self, name):
        entry = self.feeds.get(name) or {}
        ttl = (entry.get("data") or {}).get("ttl_s")
        if ttl is None and name in self.sources:
            ttl = self.sources[name].get("every_s", 300) * 3 + 60
        return ttl

    def lookup(self, ref, now):
        """"feed.widget" -> (widget, stale mark, feed name)."""
        name, _, key = ref.partition(".")
        if name == "hub":
            widgets = {
                "date": {"type": "metric", "label": f"{now.year}", "value": f"{now.month}/{now.day}",
                         "sub": f"{WEEKDAYS[now.weekday()]}曜日"},
            }
            return widgets.get(key), None, name
        entry = self.feeds.get(name)
        if not entry or not entry.get("data"):
            return None, None, name
        return entry["data"]["widgets"].get(key), render.stale_time(entry["at"], self.ttl(name), now), name

    # --- devices -------------------------------------------------------------

    def device(self, device_id):
        device = self.devices.setdefault(device_id, {})
        device.setdefault("page", 0)
        device.setdefault("interval", self.config["interval_s"])
        device.setdefault("settings", False)
        return device

    def save_devices(self):
        (self.state / "devices.json").write_text(json.dumps(self.devices, indent=1))

    def frame_path(self, device_id):
        return self.state / f"frame-{device_id}.png"

    def last_frame(self, device_id):
        if device_id not in self.frames:
            try:
                self.frames[device_id] = Image.open(self.frame_path(device_id)).convert("L")
                self.frames[device_id].load()
            except OSError:
                return None
        return self.frames[device_id]

    def render(self, device, now):
        """(image, tap targets, regions, layout key) for what the device should show."""
        mv = device.get("bat_mv")
        if device.get("settings"):
            seen = datetime.fromtimestamp(device.get("seen", 0), now.tzinfo).strftime("%m/%d %H:%M")
            info = [f"Device {device.get('id', '?')}  ·  firmware {device.get('fw', '?')}  ·  battery {mv or '?'} mV",
                    f"Last sync {seen}  ·  hub {now.strftime('%H:%M:%S')}",
                    "Pages and feeds are edited in the hub's config.toml."]
            if self.config_error:
                info.append(f"Config error: {self.config_error}")
            return (*render.render_settings(device, self.config["intervals_s"], now, mv, info), "settings")
        pages = self.pages
        if not pages:
            return (*render.render_message("No pages yet", "Add a [[page]] to the hub's config.toml. "
                                           "See hub/README.md.", now, mv), "message")
        index = device["page"] % len(pages)
        image, spots, regions = render.render_page(pages[index], lambda ref: self.lookup(ref, now),
                                                   index, len(pages), now, mv)
        return image, spots, regions, f"page:{index}:{self.config_mtime}"

    def page_feeds(self, device):
        pages = self.pages
        if not pages or device.get("settings"):
            return set()
        cells = pages[device["page"] % len(pages)].get("cells") or []
        return {str(c.get("w") or "").partition(".")[0] for c in cells} & set(self.sources)

    def apply(self, device, action):
        """Handle one action string. Returns True to force a clean full refresh."""
        pages = max(len(self.pages), 1)
        if action in ("nav:next", "nav:prev"):
            device["settings"] = False
            device["page"] = (device["page"] + (1 if action == "nav:next" else -1)) % pages
        elif action == "nav:settings":
            device["settings"] = not device["settings"]
        elif action == "set:close":
            device["settings"] = False
        elif action == "set:full":
            return True
        elif action.startswith("set:interval:"):
            seconds = int(action.rsplit(":", 1)[1])
            if seconds in self.config["intervals_s"]:
                device["interval"] = seconds
        elif action == "refresh":
            threads = [self.fetch_async(name) for name in self.page_feeds(device)]
            deadline = time.time() + 8
            for thread in threads:
                if thread:
                    thread.join(max(0, deadline - time.time()))
        elif action.startswith("feed:"):
            _, name, feed_action = action.split(":", 2)
            self.fetch(name, feed_action)
        return False

    def sync(self, request):
        """One device round trip: apply its event, render, answer with the difference."""
        device_id = str(request.get("id") or "")
        if not NAME.match(device_id):
            raise ValueError("bad device id")
        have = request.get("have") or 0
        event = request.get("ev") or {}
        with self.lock:
            self.load_config()
            device = self.device(device_id)
            device.update(id=device_id, seen=time.time(), bat_mv=request.get("bat_mv"),
                          fw=request.get("fw"), wake=request.get("wake"))
            old = self.last_frame(device_id) if have and have == device.get("frame_id") else None

            action = None
            if isinstance(event.get("tap"), list) and len(event["tap"]) == 2 and old is not None:
                tx, ty = event["tap"]
                for x, y, w, h, target in self.spots.get(device_id) or device.get("spots") or []:
                    if x <= tx < x + w and y <= ty < y + h:
                        action = target
                        break
            elif event.get("key") in ("left", "right", "press", "hold"):
                action = {"left": "nav:prev", "right": "nav:next", "press": "refresh",
                          "hold": "nav:settings"}[event["key"]]
            clean = bool(action) and self.apply(device, action)

            now = self.now()
            image, spots, regions, layout = self.render(device, now)
            levels = frame.quantize(image)
            due = (request.get("wake") == "timer" and device.get("partials", 0) > 0
                   and time.time() - device.get("last_full", 0) >= self.config["full_every_s"])
            if old is None or clean or due or layout != device.get("layout"):
                rects, mode = [(0, 0, render.W, render.H)], frame.GC16
                device.update(last_full=time.time(), partials=0)
            else:
                rects, mode = frame.changed_rects(old, levels, regions), frame.GL16
                if rects:
                    device["partials"] = device.get("partials", 0) + 1

            awake = self.config["settings_awake_s"] if device["settings"] else self.config["awake_s"]
            body = frame.encode(levels, rects, mode, device["interval"], awake, now)
            device.update(frame_id=frame.frame_id(levels), layout=layout, spots=spots,
                          last_bytes=len(body), last_rects=len(rects))
            self.frames[device_id], self.spots[device_id] = levels, spots
            print(f"device {device_id}: {request.get('wake')} {action or '-'} -> "
                  f"{['GC16', 'GL16', 'DU4'][mode]} {rects} {len(body)} bytes", flush=True)
            levels.save(self.frame_path(device_id))
            self.save_devices()
            return body

    # --- browser views -------------------------------------------------------

    def preview(self, index, settings=False):
        now = self.now()
        with self.lock:
            self.load_config()
            device = {"page": index, "settings": settings, "interval": self.config["interval_s"], "bat_mv": 3950}
            image = self.render(device, now)[0]
        out = io.BytesIO()
        frame.to_png_image(frame.quantize(image)).save(out, "PNG")
        return out.getvalue()

    def index_html(self):
        now = time.time()
        age = lambda at: "never" if not at else f"{int(now - at)} s ago"
        rows = []
        for name in sorted(set(self.feeds) | set(self.sources)):
            entry = self.feeds.get(name) or {}
            source = self.sources.get(name)
            kind = "push" if not source else f"{'exec' if source.get('exec') else 'url'} / {source.get('every_s', 300)} s"
            widgets = ", ".join(f"{name}.{key}" for key in (entry.get("data") or {}).get("widgets", {}))
            rows.append(f"<tr><td><a href='feeds/{name}'>{name}</a></td><td>{kind}</td><td>{age(entry.get('at'))}</td>"
                        f"<td>{html.escape(entry.get('error') or '')}</td><td><code>{html.escape(widgets)}</code></td></tr>")
        devices = "".join(
            f"<tr><td><a href='device/{i}/frame.png'>{i}</a></td><td>{age(d.get('seen'))}</td><td>{d.get('bat_mv')} mV</td>"
            f"<td>page {d.get('page')}, every {d.get('interval')} s</td>"
            f"<td>last answer {d.get('last_bytes')} bytes in {d.get('last_rects')} rects</td></tr>"
            for i, d in self.devices.items())
        previews = "".join(f"<p><img src='preview/{i}.png?t={int(now)}' width='960' height='540'></p>"
                           for i in range(len(self.pages)))
        error = f"<p class='e'>Config error: {html.escape(self.config_error)}</p>" if self.config_error else ""
        return f"""<!doctype html><meta charset=utf-8><title>M5Paper hub</title>
<style>body{{font:15px system-ui;margin:24px;max-width:1000px}}img{{border:1px solid #888;max-width:100%;height:auto}}
td,th{{padding:4px 10px;border-bottom:1px solid #ccc;text-align:left;vertical-align:top}}.e{{color:#b00}}</style>
<h1>M5Paper hub</h1>{error}
<h2>Devices</h2><table>{devices or '<tr><td>none yet</td></tr>'}</table>
<h2>Feeds</h2><table><tr><th>feed</th><th>source</th><th>updated</th><th>error</th><th>widgets</th></tr>{''.join(rows)}</table>
<h2>Pages</h2>{previews or '<p>No pages configured.</p>'}"""


class Handler(BaseHTTPRequestHandler):
    server_version = "m5paper-hub"

    def log_message(self, *args):
        pass

    def send(self, status, body, content_type="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def read_json(self, limit=MAX_FEED_BYTES):
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= limit:
            raise ValueError("body missing or too large")
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        hub = self.server.hub
        path = self.path.split("?")[0].rstrip("/")
        try:
            if path == "":
                self.send(200, hub.index_html(), "text/html; charset=utf-8")
            elif path == "/healthz":
                self.send(200, {"ok": True})
            elif match := re.fullmatch(r"/preview/(\d+|settings)\.png", path):
                settings = match[1] == "settings"
                self.send(200, hub.preview(0 if settings else int(match[1]), settings), "image/png")
            elif path == "/feeds":
                self.send(200, {name: {"at": e.get("at"), "error": e.get("error"),
                                       "widgets": sorted((e.get("data") or {}).get("widgets", {}))}
                                for name, e in hub.feeds.items()})
            elif (match := re.fullmatch(r"/feeds/([^/]+)", path)) and match[1] in hub.feeds:
                self.send(200, hub.feeds[match[1]].get("data") or {})
            elif (match := re.fullmatch(r"/device/([^/]+)/frame\.png", path)) and NAME.match(match[1]):
                levels = hub.last_frame(match[1])
                if levels is None:
                    return self.send(404, {"error": "no frame"})
                out = io.BytesIO()
                frame.to_png_image(levels).save(out, "PNG")
                self.send(200, out.getvalue(), "image/png")
            else:
                self.send(404, {"error": "not found"})
        except Exception as error:
            self.send(500, {"error": f"{type(error).__name__}: {error}"})

    do_HEAD = do_GET

    def do_PUT(self):
        hub = self.server.hub
        path = self.path.split("?")[0].rstrip("/")
        try:
            if match := re.fullmatch(r"/feeds/([^/]+)", path):
                token = hub.config.get("token")
                if token and self.headers.get("X-Hub-Token") != token:
                    return self.send(403, {"error": "bad or missing X-Hub-Token"})
                if not NAME.match(match[1]) or match[1] == "hub":
                    return self.send(400, {"error": "bad feed name"})
                hub.put_feed(match[1], self.read_json())
                self.send(200, {"ok": True})
            elif path == "/device/sync" and self.command == "POST":
                self.send(200, hub.sync(self.read_json(4096)), "application/octet-stream")
            else:
                self.send(404, {"error": "not found"})
        except ValueError as error:
            self.send(400, {"error": str(error)})
        except Exception as error:
            print(f"{self.command} {path}: {type(error).__name__}: {error}", flush=True)
            self.send(500, {"error": f"{type(error).__name__}: {error}"})

    do_POST = do_PUT

    def do_DELETE(self):
        hub = self.server.hub
        match = re.fullmatch(r"/feeds/([^/]+)", self.path.split("?")[0].rstrip("/"))
        token = hub.config.get("token")
        if token and self.headers.get("X-Hub-Token") != token:
            return self.send(403, {"error": "bad or missing X-Hub-Token"})
        if not match or not NAME.match(match[1]) or match[1] not in hub.feeds:
            return self.send(404, {"error": "not found"})
        with hub.lock:
            del hub.feeds[match[1]]
            (hub.state / "feeds" / f"{match[1]}.json").unlink(missing_ok=True)
        self.send(200, {"ok": True})


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", default=Path(__file__).parent / "config.toml")
    parser.add_argument("--state", default="~/.local/state/m5paper-hub")
    args = parser.parse_args()
    hub = Hub(args.config, args.state)
    render.font(20)  # Fail at start, not at the first sync, if fonts are missing.
    threading.Thread(target=hub.schedule_forever, daemon=True).start()
    server = ThreadingHTTPServer((hub.config["bind"], hub.config["port"]), Handler)
    server.hub = hub
    print(f"m5paper-hub listening on {hub.config['bind']}:{hub.config['port']}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
