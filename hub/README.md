# M5Paper hub

The server half of the M5Paper display. It collects **feeds** (small JSON documents made anywhere), lays their widgets out on **pages**, renders each page as a 960×540 16-gray image, and sends the M5Paper only the parts that changed. Taps and wheel input come back from the device and are handled here.

- Feed format: [FEEDS.md](FEEDS.md)
- Device protocol: [PROTOCOL.md](PROTOCOL.md)
- Runs as a systemd user unit, `m5paper-hub`, on any always-on Linux machine on the LAN. `hub.local` below stands for that machine.

## Look at it

Open `http://hub.local:60091/` in a browser. It shows the devices, every feed with its age and last error, and each page as the panel draws it. `/device/<id>/frame.png` is what the hub believes that device shows right now.

## Edit pages and feeds

Everything is in `~/.local/share/m5paper-hub/config.toml` on the hub machine. The hub rereads it within a second of a change; a broken file keeps the old configuration and shows the error on the browser page and the device's settings page. `config.example.toml` documents every key.

```toml
[[page]]
title = "Home"
grid = [4, 4]                                  # columns, rows
cells = [
  { w = "markets.usdjpy", at = [0, 0] },       # feed.widget at column, row
  { w = "news.headlines", at = [0, 1, 2, 3], size = 21 },   # ... colspan, rowspan; extra keys override the widget
]
```

`hub.date` is built in. A widget that does not exist yet shows `no data`.

The deployed config is the source of truth; the deploy never overwrites it. `hub/deploy.sh --pull-config user@host` copies it back to `hub/config.deployed.toml` (git-ignored).

## On the device

| Input | Effect |
|---|---|
| Wheel left / right, or tap the header arrows | Previous / next page |
| Wheel press | Refetch this page's feeds now |
| Hold the wheel 1 s, or tap ≡ | Settings: update interval, clean the screen |
| Tap a button widget | That feed's action |

The device only listens while awake: after a manual wake it stays up for `awake_s` (15 s) since the last input.

## Deploy

```sh
hub/deploy.sh user@host          # SSH_KEY=~/.ssh/id_x hub/deploy.sh ... to pick a key
```

It copies `hub/` and `feeds/` to `~/.local/share/m5paper-hub/`, installs the user units `m5paper-hub` and `m5paper-sysmon`, and restarts them. The target needs only Python 3.11+ and systemd, no sudo and no pip: the script downloads Pillow for the target's Python version into `hub/vendor/` (needs `uv` here) and copies Noto Sans CJK from this machine into `hub/fonts/` (both git-ignored). Without the CJK fonts the hub falls back to DejaVu and Japanese text will not render. It never overwrites `config.toml` on the target. State (feeds, device settings, last frames) is in `~/.local/state/m5paper-hub/`.

Logs: `journalctl --user -u m5paper-hub -f` on the hub machine. Each sync is one line: wake reason, action, update mode, rectangle, bytes.

The hub has no authentication beyond the optional feed `token`. Keep it on the LAN.

## Develop locally

```sh
cp hub/config.example.toml /tmp/hub/config.toml      # then fix the feeds/ paths and the port
uv run --no-project --with pillow python hub/hub.py --config /tmp/hub/config.toml --state /tmp/hub/state
uv run --no-project --with pillow --with pytest pytest hub/test_hub.py
```

`exec` commands run from the config file's folder.

## Files

| File | Role |
|---|---|
| `hub.py` | HTTP server, feed store and scheduler, per-device state, sync logic |
| `render.py` | Widgets, header, settings page. Pure drawing with Pillow |
| `frame.py` | Quantise to 16 levels, diff by region, encode and decode the wire format |
| `test_hub.py` | Simulates a device against the hub |
