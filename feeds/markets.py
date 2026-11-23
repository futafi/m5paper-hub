#!/usr/bin/env python3
"""Currency / crypto / stock feed from Yahoo Finance's chart endpoint.

Prints one feed (see ../hub/FEEDS.md) on stdout. For each symbol it emits a
`metric` widget (price, change, sparkline) and a `line` widget `<id>_chart`.

    python3 markets.py 'USDJPY=X:USD/JPY' 'BTC-JPY:BTC' 'ETH-JPY:ETH' '^N225:日経平均'

The endpoint is unofficial and unauthenticated; keep the interval at minutes.
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime

DEFAULT = ["USDJPY=X:USD/JPY", "BTC-JPY:BTC/JPY", "ETH-JPY:ETH/JPY", "BTC-USD:BTC/USD"]


def chart(symbol, span, interval):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?range={span}&interval={interval}")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)["chart"]["result"][0]


def price(value):
    if value >= 10000:
        return f"{value:,.0f}"
    return f"{value:,.2f}" if value >= 10 else f"{value:,.4f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("symbols", nargs="*", default=DEFAULT, help="SYMBOL[:LABEL], Yahoo Finance symbols")
    parser.add_argument("--range", default="1d")
    parser.add_argument("--interval", default="15m")
    args = parser.parse_args()

    widgets, errors = {}, []
    for spec in args.symbols:
        symbol, _, label = spec.partition(":")
        key = re.sub(r"[^a-z0-9]", "", symbol.lower().removesuffix("=x"))
        try:
            result = chart(symbol, args.range, args.interval)
            closes = result["indicators"]["quote"][0]["close"]
            stamps = result["timestamp"]
            points = [(t, c) for t, c in zip(stamps, closes) if c is not None]
            last = result["meta"].get("regularMarketPrice") or points[-1][1]
            previous = result["meta"].get("chartPreviousClose") or points[0][1]
            change = (last - previous) / previous * 100
            values = [round(c, 6) for _, c in points]
            sub = f"{change:+.2f}%  ({args.range})"
            widgets[key] = {"type": "metric", "label": label or symbol, "value": price(last),
                            "sub": sub, "trend": values}
            widgets[key + "_chart"] = {
                "type": "line", "label": f"{label or symbol}  {price(last)}", "note": sub, "values": values,
                "x": [datetime.fromtimestamp(t).strftime("%H:%M") if i % 8 == 0 else ""
                      for i, (t, _) in enumerate(points)]}
        except Exception as error:  # One bad symbol must not hide the others.
            errors.append(f"{symbol}: {type(error).__name__}: {error}")
    for line in errors:
        print(line, file=sys.stderr)
    if not widgets:
        sys.exit(1)
    json.dump({"v": 1, "title": "Markets", "ttl_s": 3600, "widgets": widgets}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
