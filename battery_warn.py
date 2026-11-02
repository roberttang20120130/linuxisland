#!/usr/bin/env python3

import glob
import json
import time
import urllib.request

ISLAND_URL = "http://127.0.0.1:8765/event"

POLL_INTERVAL = 10

BORDER = "#FF9500"

THRESHOLDS = [
    (20, "warning"),
    (10, "low"),
    (5, "critical"),
]


def notify_island(value, duration=4):
    data = json.dumps({
        "type": "battery_warning",
        "title": "🔋 Battery",
        "value": value,
        "border": BORDER,
        "border_width": 2,
        "border_radius": 16,
        "duration": duration,
    }).encode("utf-8")

    request = urllib.request.Request(
        ISLAND_URL,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    try:
        urllib.request.urlopen(request, timeout=0.5).close()
    except Exception:
        pass


def get_battery():
    batteries = glob.glob("/sys/class/power_supply/BAT*")

    if not batteries:
        return None, None

    battery = batteries[0]

    try:
        with open(f"{battery}/capacity", "r") as f:
            capacity = int(f.read().strip())

        with open(f"{battery}/status", "r") as f:
            status = f.read().strip()

        return capacity, status

    except (OSError, ValueError):
        return None, None


def get_threshold(capacity):
    for threshold, name in THRESHOLDS:
        if capacity <= threshold:
            return threshold, name

    return None, "normal"


def main():
    last_triggered = None

    while True:
        capacity, status = get_battery()

        if capacity is not None:

            # Don't warn while charging.
            if status not in ("Charging", "Full"):

                threshold, state = get_threshold(capacity)

                if threshold is not None:

                    # Only fire once for each threshold.
                    if last_triggered != threshold:
                        notify_island(
                            f"{capacity}% remaining",
                            4
                        )

                        last_triggered = threshold

                else:
                    # Battery has recovered above 20%.
                    last_triggered = None

            else:
                # Reset warnings when charging.
                last_triggered = None

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()