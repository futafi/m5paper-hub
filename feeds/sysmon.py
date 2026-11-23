#!/usr/bin/env python3
"""CPU / memory / disk feed for the Linux machine it runs on.

Shows the push model: run it on any PC and it PUTs to the hub by itself.

    python3 sysmon.py --hub http://hub.local:60091 --name sysmon-desk --every 60

Without --hub it prints one feed on stdout (see ../hub/FEEDS.md).
"""

import argparse
import json
import os
import shutil
import socket
import sys
import time
import urllib.request


def cpu_times():
    with open("/proc/stat") as stat:
        fields = [int(v) for v in stat.readline().split()[1:]]
    return sum(fields), fields[3] + fields[4]  # total, idle + iowait


def memory():
    info = {}
    with open("/proc/meminfo") as meminfo:
        for line in meminfo:
            key, value = line.split(":")
            info[key] = int(value.split()[0]) * 1024
    return info["MemTotal"] - info["MemAvailable"], info["MemTotal"]


def sample(before, history, host, path):
    after = cpu_times()
    busy = 100 * (1 - (after[1] - before[1]) / max(after[0] - before[0], 1))
    history.append(round(busy, 1))
    del history[:-60]
    used, total = memory()
    disk = shutil.disk_usage(path)
    gib = 1 << 30
    load = os.getloadavg()
    widgets = {
        "cpu": {"type": "metric", "label": f"{host} CPU", "value": f"{busy:.0f}", "unit": "%",
                "sub": f"load {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}", "trend": list(history)},
        "mem": {"type": "gauge", "label": f"{host} memory", "value": used, "max": total,
                "text": f"{used / gib:.1f} / {total / gib:.1f} GiB"},
        "disk": {"type": "gauge", "label": f"{host} disk {path}", "value": disk.used, "max": disk.total,
                 "text": f"{disk.used / gib:.0f} / {disk.total / gib:.0f} GiB"},
    }
    return after, {"v": 1, "title": host, "widgets": widgets}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--hub", help="hub base URL; omit to print once")
    parser.add_argument("--name", default=None, help="feed name (default: sysmon-<hostname>)")
    parser.add_argument("--every", type=int, default=60, help="seconds between pushes")
    parser.add_argument("--path", default="/", help="filesystem to report")
    parser.add_argument("--token", default=os.environ.get("HUB_TOKEN", ""))
    args = parser.parse_args()
    host = socket.gethostname().split(".")[0]
    name = args.name or f"sysmon-{host.lower()}"
    history, before = [], cpu_times()

    if not args.hub:
        time.sleep(1)
        json.dump(sample(before, history, host, args.path)[1], sys.stdout, ensure_ascii=False)
        return
    while True:
        time.sleep(args.every)
        before, feed = sample(before, history, host, args.path)
        feed["ttl_s"] = args.every * 3 + 30
        request = urllib.request.Request(f"{args.hub.rstrip('/')}/feeds/{name}", method="PUT",
                                         data=json.dumps(feed).encode(),
                                         headers={"Content-Type": "application/json", "X-Hub-Token": args.token})
        try:
            urllib.request.urlopen(request, timeout=10).read()
        except OSError as error:
            print(f"push failed: {error}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
