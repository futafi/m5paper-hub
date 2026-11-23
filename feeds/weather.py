#!/usr/bin/env python3
"""Weather feed from Open-Meteo (no API key). Default location: Tokyo.

Prints one feed (see ../hub/FEEDS.md): `now` (metric), `temp` (line, next 24 h)
and `rain` (bars, precipitation probability for the next 24 h).
"""

import argparse
import json
import sys
import urllib.request

# WMO weather interpretation codes.
CODES = {0: "快晴", 1: "晴れ", 2: "晴れ時々曇り", 3: "曇り", 45: "霧", 48: "霧", 51: "霧雨", 53: "霧雨", 55: "霧雨",
         61: "弱い雨", 63: "雨", 65: "強い雨", 66: "着氷性の雨", 67: "着氷性の雨", 71: "弱い雪", 73: "雪", 75: "大雪",
         77: "霧雪", 80: "にわか雨", 81: "にわか雨", 82: "激しいにわか雨", 85: "にわか雪", 86: "にわか雪",
         95: "雷雨", 96: "雷雨とひょう", 99: "雷雨とひょう"}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--lat", type=float, default=35.68)
    parser.add_argument("--lon", type=float, default=139.76)
    parser.add_argument("--place", default="東京")
    args = parser.parse_args()

    url = ("https://api.open-meteo.com/v1/forecast?"
           f"latitude={args.lat}&longitude={args.lon}&timezone=auto&forecast_days=2"
           "&current=temperature_2m,weather_code,relative_humidity_2m"
           "&hourly=temperature_2m,precipitation_probability"
           "&daily=temperature_2m_max,temperature_2m_min")
    with urllib.request.urlopen(url, timeout=15) as response:
        data = json.load(response)
    current, hourly, daily = data["current"], data["hourly"], data["daily"]
    start = next((i for i, t in enumerate(hourly["time"]) if t >= current["time"][:13]), 0)
    hours = slice(start, start + 24)
    labels = [t[11:13] if int(t[11:13]) % 3 == 0 else "" for t in hourly["time"][hours]]
    sky = CODES.get(current["weather_code"], f"code {current['weather_code']}")
    widgets = {
        "now": {"type": "metric", "label": f"{args.place}  {sky}", "value": f"{current['temperature_2m']:.1f}",
                "unit": "°C",
                "sub": f"{daily['temperature_2m_min'][0]:.0f}° – {daily['temperature_2m_max'][0]:.0f}°"
                       f"  湿度{current['relative_humidity_2m']}%"},
        "temp": {"type": "line", "label": "気温 24時間", "values": hourly["temperature_2m"][hours], "x": labels},
        "rain": {"type": "bars", "label": "降水確率 24時間",
                 "note": f"最大 {max(v or 0 for v in hourly['precipitation_probability'][hours])}%",
                 "values": hourly["precipitation_probability"][hours], "x": labels},
    }
    json.dump({"v": 1, "title": "Weather", "ttl_s": 3 * 3600, "widgets": widgets}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
