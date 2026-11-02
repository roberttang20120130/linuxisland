#!/usr/bin/env python3

import http.client
import json
import subprocess
import threading
import time


ISLAND_HOST = "127.0.0.1"
ISLAND_PORT = 8765
ISLAND_PATH = "/event"

DISCONNECT_GRACE = 5.0

BORDER = "#2196F3"


def notify_island(value, duration=3):
    payload = json.dumps({
        "type": "wifi",
        "title": "📶 Wi-Fi",
        "value": value,
        "border": BORDER,
        "border_width": 2,
        "border_radius": 16,
        "duration": duration,
    }).encode("utf-8")

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
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            },
        )

        response = connection.getresponse()
        response.read()

    except OSError:
        pass

    finally:
        if connection is not None:
            connection.close()


def get_wifi_state():
    try:
        result = subprocess.run(
            [
                "nmcli",
                "-t",
                "-f",
                "TYPE,STATE,CONNECTION",
                "device",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )

        for line in result.stdout.splitlines():
            parts = line.split(":", 2)

            if len(parts) != 3:
                continue

            device_type, state, connection = parts

            if device_type != "wifi":
                continue

            if state == "connected":
                return "connected", connection

            return "disconnected", None

    except (OSError, subprocess.SubprocessError):
        pass

    return "unknown", None


class WiFiWatcher:
    def __init__(self):
        self.confirmed_state = "unknown"
        self.confirmed_connection = None

        self.disconnect_timer = None
        self.lock = threading.Lock()

    def cancel_disconnect_timer(self):
        if self.disconnect_timer is not None:
            self.disconnect_timer.cancel()
            self.disconnect_timer = None

    def confirm_disconnect(self):
        with self.lock:
            self.disconnect_timer = None

            state, connection = get_wifi_state()

            # Wi-Fi came back during the grace period.
            if state == "connected":
                self.handle_connected(connection)
                return

            if state != "disconnected":
                return

            if self.confirmed_state == "disconnected":
                return

            self.confirmed_state = "disconnected"
            self.confirmed_connection = None

        notify_island("Disconnected", 4)

    def handle_connected(self, connection):
        with self.lock:
            self.cancel_disconnect_timer()

            if self.confirmed_state != "connected":
                self.confirmed_state = "connected"
                self.confirmed_connection = connection

                should_notify = bool(connection)

            elif connection != self.confirmed_connection:
                self.confirmed_connection = connection

                should_notify = bool(connection)

            else:
                should_notify = False

        if should_notify:
            notify_island(connection, 3)

    def handle_state_change(self):
        state, connection = get_wifi_state()

        if state == "connected":
            self.handle_connected(connection)
            return

        if state != "disconnected":
            return

        with self.lock:
            if self.confirmed_state == "disconnected":
                return

            if self.disconnect_timer is not None:
                return

            self.disconnect_timer = threading.Timer(
                DISCONNECT_GRACE,
                self.confirm_disconnect,
            )

            self.disconnect_timer.daemon = True
            self.disconnect_timer.start()

    def run(self):
        print("Wi-Fi watcher started.")

        # Establish initial state without notification.
        state, connection = get_wifi_state()

        if state == "connected":
            self.confirmed_state = "connected"
            self.confirmed_connection = connection

        elif state == "disconnected":
            self.confirmed_state = "disconnected"

        print(
            f"Initial Wi-Fi state: "
            f"{self.confirmed_state}"
        )

        process = subprocess.Popen(
            ["nmcli", "monitor"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

        try:
            for line in process.stdout:
                self.handle_state_change()

        except KeyboardInterrupt:
            pass

        finally:
            self.cancel_disconnect_timer()

            process.terminate()

            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    WiFiWatcher().run()
