#!/usr/bin/env python3

import json
import urllib.request

import pyudev


ISLAND_URL = "http://127.0.0.1:8765/event"

BORDER = "#9C27B0"


def notify_island(value, duration=3):
    data = json.dumps({
        "type": "usb",
        "title": "🔌 USB",
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
        urllib.request.urlopen(
            request,
            timeout=0.5
        ).close()

    except Exception:
        pass


def get_device_name(device):
    """
    Try to get a useful human-readable USB device name.
    """

    # Most USB devices expose PRODUCT.
    product = device.get("ID_PRODUCT")

    if product:
        return product

    # Fall back to the kernel-reported product name.
    product = device.get("PRODUCT")

    if product:
        return product

    # Fall back to model.
    model = device.get("ID_MODEL")

    if model:
        return model

    return "USB device"


def usb_event(device):
    """
    Handle a udev USB event.
    """

    action = device.action

    # We only care about actual USB device insertion/removal.
    if action not in ("add", "remove"):
        return

    # Ignore USB interfaces.
    #
    # A single physical USB device can generate multiple
    # interface events. We only want the parent USB device.
    if device.device_type != "usb_device":
        return

    name = get_device_name(device)

    if action == "add":
        notify_island(
            f"{name} connected",
            3
        )

        print(f"USB connected: {name}")

    elif action == "remove":
        notify_island(
            f"{name} disconnected",
            3
        )

        print(f"USB disconnected: {name}")


def main():
    context = pyudev.Context()

    monitor = pyudev.Monitor.from_netlink(context)

    # Only listen for USB subsystem events.
    monitor.filter_by(subsystem="usb")

    print("USB watcher started.")

    for device in iter(monitor.poll, None):
        try:
            usb_event(device)

        except Exception as error:
            print("USB event error:", error)


if __name__ == "__main__":
    main()