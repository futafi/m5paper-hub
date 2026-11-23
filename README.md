# m5paper-hub

Turn an **M5Paper** (the original v1.1, 4.7" e-ink) into a battery-powered wall display for anything you can describe in a little JSON: prices, server load, headlines, weather, your own dashboards.

```
feeds (anywhere)  --JSON-->  hub (a Linux box on your LAN)  --changed pixels-->  M5Paper
                             renders pages                  <--taps, wheel-----
```

- **Feeds** are small JSON documents listing widgets (a number, a chart, a list of headlines, buttons). Any script on any machine can make one and push it, or the hub can run the script itself.
- **The hub** lays widgets out on pages, renders them at the panel's native 960×540 in 16 grays, and sends the device only what changed, usually a few kilobytes.
- **The device** is a thin client. It wakes on a timer, asks the hub what to draw, and powers off. New content, new widget types and new layouts never need a firmware flash.
- **Input** goes back to the hub: the wheel turns pages, taps press buttons that a feed defined.

| Directory | What | Start here |
|---|---|---|
| [`hub/`](hub/README.md) | Server: stores feeds, renders pages, answers the device | [feed format](hub/FEEDS.md), [device protocol](hub/PROTOCOL.md) |
| [`device/`](device/README.md) | Thin-client firmware (PlatformIO) | |
| [`feeds/`](feeds/README.md) | Sample feeds: markets, news, weather, system monitor, and one with actions | |

## Quick start

1. **Hub.** On a machine with `uv`, `hub/deploy.sh user@host` installs the hub and the sample feeds on an always-on Linux box and starts them. Open `http://<host>:60091/` to see the pages as the panel will draw them. To try it locally first, see [hub/README.md](hub/README.md#develop-locally).
2. **Device.** Copy `device/include/secrets.h.example` to `secrets.h`, fill in Wi-Fi and the hub address, then build and flash ([device/README.md](device/README.md)).
3. **Your own content.** Write a script that prints a feed (copy one from `feeds/`), push it with `curl -X PUT http://<host>:60091/feeds/<name>` or add it to the hub config, and place its widgets on a page in `config.toml`. The M5Paper picks it up at its next wake.

## Status

Built for one M5Paper on a home LAN. The hub has no authentication beyond an optional token for pushing feeds, and the device speaks plain HTTP: do not expose either to the internet. Page layout is edited in a config file; there is no browser editor or firmware OTA yet.

## License

MIT. See [LICENSE](LICENSE).
