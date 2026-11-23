#!/usr/bin/env python3
"""Reset the M5Paper over USB, log its serial output, and optionally inject events.

    uvx --from pyserial python tools/serial_test.py [--port /dev/ttyUSB0] [--seconds 30] [event ...]

Events are the firmware's serial test commands (see src/main.cpp): l, r, p, h,
or "t X Y" for a tap. They are sent a few seconds apart once the first sync is done.
Resetting counts as a manual wake, so the device stays awake to take them.
"""

import argparse
import sys
import time

import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("events", nargs="*")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--gap", type=float, default=4, help="seconds between events")
    parser.add_argument("--no-reset", action="store_true")
    args = parser.parse_args()

    port = serial.Serial()
    port.port, port.baudrate, port.timeout = args.port, 115200, 0.2
    port.dtr = port.rts = False
    port.open()
    if not args.no_reset:  # Pulse EN through RTS, with GPIO0 (DTR) left high.
        port.rts = True
        time.sleep(0.1)
        port.rts = False
    start, events, next_event, buffer = time.time(), list(args.events), None, b""
    while time.time() - start < args.seconds:
        buffer += port.read(256)
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            text = line.decode(errors="replace").rstrip()
            print(f"{time.time() - start:6.2f}  {text}", flush=True)
            if text.startswith(("Sync ok", "Sync failed")) and events:
                next_event = time.time() + args.gap
        if next_event and time.time() >= next_event and events:
            event = events.pop(0)
            print(f"{time.time() - start:6.2f}  >>> {event}", flush=True)
            port.write(event.encode() + b"\n")
            next_event = None
    if events:
        sys.exit(f"not sent: {events}")


if __name__ == "__main__":
    main()
