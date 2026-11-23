# Feed format (v1)

A feed is one JSON object that describes a few **widgets**. You write a feed anywhere, in any language; the hub draws it. Pages on the M5Paper are built from widgets by name, `feed.widget`.

```json
{
  "v": 1,
  "title": "Markets",
  "ttl_s": 3600,
  "widgets": {
    "usdjpy": { "type": "metric", "label": "USD/JPY", "value": "159.15", "sub": "+0.40%" }
  }
}
```

| Field | Meaning |
|---|---|
| `v` | Must be `1`. |
| `title` | Free text, shown in the hub's browser page. |
| `ttl_s` | Optional. After this many seconds without an update, the widgets are marked `stale HH:MM`. Default for fetched feeds: three intervals plus a minute; pushed feeds never go stale without it. |
| `widgets` | Object of widget id → widget. Ids use `a-z 0-9 _ -`, up to 32 characters. |

A feed may be at most 256 KB. The whole feed is replaced on each update.

## Delivering a feed

**Push** from any machine. No hub configuration is needed; the feed name is the last part of the address (`a-z 0-9 _ -`).

```sh
python3 my_feed.py | curl -fsS -X PUT --data-binary @- http://hub.local:60091/feeds/my-feed
```

If the hub has a `token`, add `-H "X-Hub-Token: <token>"`. `DELETE /feeds/<name>` removes a feed.

**Fetched by the hub.** Add an entry to the hub's `config.toml`:

```toml
[feed.my-feed]
exec = ["python3", "/path/to/my_feed.py"]   # prints the feed on stdout; or:
# url = "http://other-pc:9000/feed.json"    # returns the feed
every_s = 300
timeout_s = 20
```

Only fetched feeds can have **actions** (below), because the hub has to ask the feed again right after a tap.

## Widgets

Every widget has `type` and usually `label`. `note` is small text at the right of the label row. Unknown keys are ignored. A page cell can override any key (for example `size`) in the hub config.

| `type` | Keys | Draws |
|---|---|---|
| `metric` | `value`, `unit`, `sub`, `trend` (numbers) | One big value, a line of small text, an optional sparkline. |
| `bars` | `values` (numbers) or `series` (`[{name, values}]`, up to 3, stacked), `x` (labels) | Bar chart. Negative values hang below a zero line. |
| `line` | `values` or `series`, `x` | Line chart with min and max. |
| `gauge` | `value`, `max` (default 100), `text` | Text over a filled bar. |
| `list` | `items` (strings or `{text, sub, value}`), `size` (px, default 22), `lines` (per item, default 2) | Wrapped rows, for headlines. Japanese wraps anywhere. `value` (string or number) is drawn at the right edge of the row, for name–number tables. |
| `text` | `text`, `size` (default 24) | Wrapped paragraph. |
| `buttons` | `options`: `[{label, action, selected}]` | A row of buttons. See Actions. |

`value` may be a string (shown as is) or a number. Format prices and units yourself if you care how they look. `x` should have one label per value; use `""` for points without a label. The hub drops labels that would overlap.

The panel has 16 gray levels and is 960×540. A cell in a 4×4 grid is about 240×124 px: a `metric` fits, a chart wants two cells.

## Actions

A `buttons` option with an `action` string is a tap target, unless it is `selected`. When tapped, the hub fetches the feed again with the action and draws the answer immediately:

- `exec` feeds are run with `--action <string>` appended.
- `url` feeds get `POST` with the body `{"action": "<string>"}`.

Either way, answer with the complete, updated feed. Keep any state yourself (see `feeds/strata.py`, which remembers the chosen range in a file). An action has up to `timeout_s` to finish; the device waits about 20 s.

## Trying a feed

Open the hub in a browser (`http://hub.local:60091/`). It lists every feed with its age, last error and widget names, and shows each page exactly as the panel draws it.
