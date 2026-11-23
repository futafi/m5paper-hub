# Notes for agents working on the hub

Read `README.md`, `FEEDS.md` and `PROTOCOL.md` first. They are the contract; keep them true when you change behaviour.

- **Three contracts, change them deliberately.** The feed format (`FEEDS.md`, checked by `check_feed`), the wire format (`PROTOCOL.md`, `frame.py`, `device/src/net.cpp`) and `STATUS_RECT` (`render.py` and `device/src/screen.h`). A wire or `STATUS_RECT` change needs a firmware flash; a feed format change breaks feeds other people wrote. Adding a widget type or an optional key needs neither.
- **The device image must equal the hub's.** `test_hub.py` decodes every response onto a canvas and compares frame ids. Run it after any change to `frame.py`, `render.py` or `Hub.sync`.
- **Draw only with the 16 gray levels** (`BLACK` … `WHITE` in `render.py`); anything else changes when quantised. x and width of sent rectangles must be multiples of 4 (`changed_rects` does this).
- **Regions.** `render_*` returns the rectangles that change independently; the hub diffs inside each. Anything drawn outside every region is never updated partially.
- **Check the picture.** Start a local hub and read `/preview/<n>.png`. You cannot see the panel; `/device/<id>/frame.png` on the real hub is the closest thing.
- **The deployed `config.toml` belongs to the hub machine.** `hub/deploy.sh` never overwrites it; do not either. The deploy needs no sudo and no pip on the target.
- `Hub.sync` holds the lock while a feed action runs, so one slow action delays other requests. Keep feed `timeout_s` short.
- Not built yet: a browser editor for page layout, firmware OTA, quiet hours.
