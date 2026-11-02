#!/usr/bin/env python3

import json
import time
import urllib.request

ISLAND_URL = "http://127.0.0.1:8765/event"

POLL_INTERVAL = 2

# Temperature thresholds
WARNING_TEMP = 75
HIGH_TEMP = 85
CRITICAL_TEMP = 95

BORDER = "#FF3B30"


def notify_island(title, value, duration=3):
    data = json.dumps({
        "type": "temperature",
        "title": title,
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


def get_cpu_temperature():
    try:
        import psutil

        temps = psutil.sensors_temperatures()

        # Try common CPU temperature sensor names first
        for name in ("k10temp", "coretemp", "zenpower"):
            if name in temps:
                readings = temps[name]

                valid = [
                    r.current
                    for r in readings
                    if r.current is not None
                ]

                if valid:
                    return max(valid)

        # Fallback: first usable temperature sensor
        for readings in temps.values():
            valid = [
                r.current
                for r in readings
                if r.current is not None
            ]

            if valid:
                return max(valid)

    except Exception:
        pass

    return None


def get_state(temp):
    if temp >= CRITICAL_TEMP:
        return "critical"

    if temp >= HIGH_TEMP:
        return "high"

    if temp >= WARNING_TEMP:
        return "warning"

    return "normal"


def main():
    previous_state = "normal"

    while True:
        temp = get_cpu_temperature()

        if temp is not None:
            state = get_state(temp)

            # Only notify when crossing a threshold.
            if state != previous_state:

                if state == "warning":
                    notify_island(
                        "🌡️ CPU",
                        f"{temp:.0f}°C",
                        3
                    )

                elif state == "high":
                    notify_island(
                        "🌡️ CPU",
                        f"{temp:.0f}°C",
                        4
                    )

                elif state == "critical":
                    notify_island(
                        "🌡️ CPU",
                        f"{temp:.0f}°C",
                        5
                    )

                elif state == "normal" and previous_state != "normal":
                    notify_island(
                        "🌡️ CPU",
                        f"{temp:.0f}°C",
                        3
                    )

            previous_state = state

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()