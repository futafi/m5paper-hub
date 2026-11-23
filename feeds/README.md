# Sample feeds

Each script here is a complete, independent feed for the [M5Paper hub](../hub/README.md): standard library only, prints one feed JSON on stdout. Copy one as a starting point; a feed can live in any directory or on any machine. The format is in [../hub/FEEDS.md](../hub/FEEDS.md).

| Script | Widgets | Source |
|---|---|---|
| `strata.py` | `tok_s`, `input`, `cache`, `output`, `input_chart`, `output_chart`, `gpu`, `vram`, `range`, `power` | The author's own LLM usage dashboard, so it will not run elsewhere. Kept as the worked example of a feed with **actions** (`range:1h`, `range:24h`, `power:<watts>`) and remembered state |
| `markets.py` | `<id>` and `<id>_chart` per symbol, e.g. `usdjpy`, `btcjpy` | Yahoo Finance chart endpoint (unofficial, no key). Currencies, crypto, stocks, indices |
| `news.py` | `headlines` | Any RSS or Atom URL. Default: NHK |
| `weather.py` | `now`, `temp`, `rain` | Open-Meteo (no key). Default: Tokyo |
| `sysmon.py` | `cpu`, `mem`, `disk` | `/proc` on the machine it runs on. Pushes by itself |

## Two ways to connect a feed

**The hub runs it** (`markets`, `news`, `weather` in the example config). Add to the hub's `config.toml`:

```toml
[feed.stocks]
exec = ["python3", "feeds/markets.py", "^N225:日経平均", "7203.T:トヨタ"]
every_s = 300
```

**It pushes** from wherever it runs (`sysmon`):

```sh
python3 sysmon.py --hub http://hub.local:60091 --every 60     # feed name: sysmon-<hostname>
python3 weather.py | curl -fsS -X PUT --data-binary @- http://hub.local:60091/feeds/weather-osaka
```

`m5paper-sysmon.service` is a systemd user unit for the first form; `hub/deploy.sh` installs it on the hub machine as the feed `sysmon`. To monitor another PC, copy `sysmon.py` and the unit there, point `--hub` at the hub and pick another `--name`.

Then place the widgets on a page in the hub config, e.g. `{ w = "stocks.n225", at = [0, 0] }`.
