#!/usr/bin/env python3
"""Headline feed from any RSS or Atom URL (default: NHK ニュース 主要).

Prints one feed (see ../hub/FEEDS.md) with a single `list` widget `headlines`.

    python3 news.py --url https://hnrss.org/frontpage --title "Hacker News"
"""

import argparse
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime


def local(tag):
    return tag.rsplit("}", 1)[-1]


def when(text):
    if not text:
        return ""
    try:
        stamp = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return ""
    stamp = stamp.astimezone()
    return stamp.strftime("%H:%M" if stamp.date() == datetime.now().astimezone().date() else "%m/%d %H:%M")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default="https://news.web.nhk/n-data/conf/na/rss/cat0.xml")
    parser.add_argument("--title", default="NHK ニュース")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--size", type=int, default=24, help="headline font size in px")
    args = parser.parse_args()

    request = urllib.request.Request(args.url, headers={"User-Agent": "m5paper-feed"})
    with urllib.request.urlopen(request, timeout=15) as response:
        root = ET.fromstring(response.read())
    items = []
    for node in root.iter():
        if local(node.tag) not in ("item", "entry"):
            continue
        fields = {local(child.tag): (child.text or "").strip() for child in node}
        if fields.get("title"):
            stamp = when(fields.get("pubDate") or fields.get("updated") or fields.get("published") or fields.get("date"))
            items.append({"text": fields["title"], "sub": stamp})
        if len(items) >= args.count:
            break
    if not items:
        sys.exit("no items in feed")
    widget = {"type": "list", "label": args.title, "items": items, "size": args.size, "lines": 2}
    json.dump({"v": 1, "title": args.title, "ttl_s": 7200, "widgets": {"headlines": widget}},
              sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
