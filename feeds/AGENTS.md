# Notes for agents writing feeds

- The contract is `../hub/FEEDS.md`. A feed is valid if `PUT /feeds/<name>` returns 200; the error text says what is wrong otherwise.
- Keep feeds self-contained: standard library only, no imports from the hub or from each other, so a script can be copied to another directory or machine unchanged.
- Print only the feed on stdout; diagnostics go to stderr. Exit non-zero on failure and the hub keeps the last good data and shows the error on its browser page.
- Format values as strings yourself. The hub does not know currencies or units.
- Run the script by hand, then check the drawing at `http://hub.local:60091/` (or a local hub's `/preview/<n>.png`).
- Actions: handle `--action <string>` and print the full updated feed. Keep state in your own file (`strata.py` uses `~/.local/state/m5paper-feeds/`). `power:<watts>` in `strata.py` changes the real GPU power limit of the machine strata-usage runs on; do not trigger it in tests.
- Be polite to public APIs: minutes, not seconds, between requests.
