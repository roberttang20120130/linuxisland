#!/usr/bin/env python3

import json
import os
import time
import http.client

ISLAND_HOST = "127.0.0.1"
ISLAND_PORT = 8765
ISLAND_PATH = "/event"

POWER_SUPPLIES = (
    "/sys/class/power_supply/BAT0",
    "/sys/class/power_supply/BATT",
)

POLL_INTERVAL = 1.0
CHARGING_GRACE_PERIOD = 1.0


def find_power_supply():
    """Find the first usable battery power supply."""
    for base in POWER_SUPPLIES:
        status_file = os.path.join(base, "status")
        capacity_file = os.path.join(base, "capacity")

        if os.path.isfile(status_file) and os.path.isfile(capacity_file):
            return status_file, capacity_file

    return None, None


STATUS_FILE, CAPACITY_FILE = find_power_supply()


def get_power_supply():
    """Read current charging state and battery percentage."""
    if STATUS_FILE is None:
        return None, None

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            status = f.read().strip().lower()

        with open(CAPACITY_FILE, "r", encoding="utf-8") as f:
            battery = int(f.read().strip())

        return status, battery

    except (OSError, ValueError):
        return None, None


def notify_island(battery):
    """Send a charging notification to Dynamic Island."""
    payload = json.dumps({
        "type": "charging",
        "battery": battery,
        "duration": 2,
    })

    connection = None

    try:
        connection = http.client.HTTPConnection(
            ISLAND_HOST,
            ISLAND_PORT,
            timeout=0.5,
        )

        connection.request(
            "POST",
            ISLAND_PATH,
            body=payload.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload.encode("utf-8"))),
            },
        )

        response = connection.getresponse()
        response.read()

        if 200 <= response.status < 300:
            print(f"Charging event sent: {battery}%")
        else:
            print(f"Island returned HTTP {response.status}")

    except OSError as error:
        print("Failed to notify island:", error)

    finally:
        if connection is not None:
            connection.close()


def main():
    print("Charging module started.")

    if STATUS_FILE is None:
        print("No supported battery power supply found.")
        return

    print(f"Monitoring: {os.path.dirname(STATUS_FILE)}")

    last_status, _ = get_power_supply()

    if last_status is None:
        print("Unable to read initial power state.")
        return

    print(f"Initial power state: {last_status}")

    while True:
        status, battery = get_power_supply()

        if status is None:
            time.sleep(POLL_INTERVAL)
            continue

        # Charger just plugged in.
        if status == "charging" and last_status != "charging":
            print(
                f"Charging detected, waiting "
                f"{CHARGING_GRACE_PERIOD}s..."
            )

            time.sleep(CHARGING_GRACE_PERIOD)

            confirmed_status, confirmed_battery = get_power_supply()

            if confirmed_status == "charging":
                print(
                    f"Charger confirmed: "
                    f"{confirmed_battery}%"
                )
                notify_island(confirmed_battery)

            else:
                print(
                    "Charging cancelled: "
                    f"power state is {confirmed_status}"
                )

            last_status = confirmed_status

        elif status != last_status:
            print(
                f"Power state: "
                f"{last_status} -> {status}"
            )
            last_status = status

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
