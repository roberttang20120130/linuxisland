#!/usr/bin/env python3

import json
import re
import subprocess
import urllib.request

ISLAND_URL = "http://127.0.0.1:8765/event"


def get_volume():
    try:
        result = subprocess.run(
            [
                "pactl",
                "get-sink-volume",
                "@DEFAULT_SINK@",
            ],
            capture_output=True,
            text=True,
            timeout=1,
        )

        match = re.search(r"/\s*(\d+)%", result.stdout)

        if match:
            return int(match.group(1))

    except Exception:
        pass

    return None


def notify_island(volume):
    data = json.dumps({
        "type": "volume",
        "volume": volume,
        "duration": 3,
    }).encode("utf-8")

    request = urllib.request.Request(
        ISLAND_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        urllib.request.urlopen(request, timeout=0.5).close()

    except Exception:
        pass


print("Volume module started.")

# Get the current volume once so startup does not trigger a notification.
last_volume = get_volume()

process = subprocess.Popen(
    ["pactl", "subscribe"],
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
    bufsize=1,
)

for line in process.stdout:
    if "change' on sink" not in line:
        continue

    volume = get_volume()

    if volume is None:
        continue

    # Ignore sink changes that did not actually change the volume.
    if volume == last_volume:
        continue

    last_volume = volume

    print(f"Volume changed: {volume}%")
    notify_island(volume)