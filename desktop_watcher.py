#!/usr/bin/env python3
"""
Desktop / workspace watcher for LinuxIsland.

Expands the island to show which virtual desktop (workspace) is active.
Supports Hyprland via its v2 event socket, with a polling fallback
for other Wayland compositors that expose `wlr-randr` or similar tools.

Compatible with any compositor: if no specific backend is detected,
falls back to periodic polling of the active workspace name.
"""

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request


ISLAND_URL = "http://127.0.0.1:8765/event"

BORDER = "#4FC3F7"

# How long the island stays expanded after a workspace switch.
DISPLAY_DURATION = 2.0

# Polling interval for the fallback backend (seconds).
POLL_INTERVAL = 1.0


def notify_island(workspace_id, workspace_name):
    """Send a desktop-switch event to the island."""
    label = f"{workspace_name}" if workspace_name else str(workspace_id)

    data = json.dumps({
        "type": "desktop",
        "title": "Desktop",
        "value": label,
        "icon": "🖥️",
        "border": BORDER,
        "border_width": 2,
        "border_radius": 16,
        "duration": DISPLAY_DURATION,
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


# ============================================================
# Hyprland backend (event socket)
# ============================================================

def find_hyprland_event_socket():
    """Locate the Hyprland v2 event socket."""
    runtime_dir = os.environ.get(
        "XDG_RUNTIME_DIR",
        f"/run/user/{os.getuid()}",
    )

    hypr_base = os.path.join(runtime_dir, "hypr")

    if not os.path.isdir(hypr_base):
        return None

    for instance in os.listdir(hypr_base):
        sock_path = os.path.join(
            hypr_base, instance, ".socket2.sock"
        )
        if os.path.exists(sock_path):
            return sock_path

    return None


def get_hyprland_active_workspace():
    """Query the current active workspace via hyprctl."""
    try:
        result = subprocess.run(
            ["hyprctl", "-j", "activeworkspace"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        data = json.loads(result.stdout)
        return data.get("id"), data.get("name")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, None


def run_hyprland_watcher():
    """Watch workspace changes via the Hyprland v2 event socket."""
    sock_path = find_hyprland_event_socket()

    if sock_path is None:
        print("desktop_watcher: Hyprland event socket not found.")
        return False

    print(f"desktop_watcher: using Hyprland socket {sock_path}", flush=True)

    # Get initial state so we don't fire on startup.
    last_id, _ = get_hyprland_active_workspace()

    while True:
        sock = None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(sock_path)
            sock.settimeout(None)

            buffer = ""

            while True:
                chunk = sock.recv(4096).decode("utf-8", errors="replace")

                if not chunk:
                    break

                buffer += chunk

                # Process complete lines.
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    # v2 workspace events look like: "workspacev2>>1,1"
                    # or legacy: "workspace>>1"
                    if not line.startswith("workspace"):
                        continue

                    payload = line.split(">>", 1)

                    if len(payload) != 2:
                        continue

                    parts = payload[1].split(",")

                    try:
                        ws_id = int(parts[0])
                    except (ValueError, IndexError):
                        continue

                    ws_name = parts[1] if len(parts) > 1 else str(ws_id)

                    if last_id is not None and ws_id == last_id:
                        continue

                    last_id = ws_id

                    print(f"desktop_watcher: workspace -> {ws_name}", flush=True)
                    notify_island(ws_id, ws_name)

        except (OSError, socket.timeout):
            # Socket disconnected (Hyprland restart). Retry.
            time.sleep(2)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass


# ============================================================
# Generic polling fallback
# ============================================================

def get_workspace_generic():
    """
    Try to detect the active workspace on non-Hyprland compositors.
    Returns (id, name) or (None, None).
    """
    # Sway: swaymsg -t get_tree is heavy; use get_outputs + focus instead.
    if shutil.which("swaymsg"):
        try:
            result = subprocess.run(
                ["swaymsg", "-t", "get_tree"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            tree = json.loads(result.stdout)

            def find_focused_workspace(node):
                if node.get("type") == "workspace" and node.get("focused"):
                    return node.get("num"), node.get("name")
                for child in node.get("nodes", []):
                    found = find_focused_workspace(child)
                    if found:
                        return found
                for child in node.get("floating_nodes", []):
                    found = find_focused_workspace(child)
                    if found:
                        return found
                return None, None

            return find_focused_workspace(tree)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass

    # Fwlux / other compositors with a CLI — extend here as needed.

    return None, None


def run_polling_watcher():
    """Generic fallback: poll for workspace changes."""
    print("desktop_watcher: using generic polling mode.", flush=True)

    last_id = None
    _, last_name = get_workspace_generic()

    while True:
        ws_id, ws_name = get_workspace_generic()

        if ws_id is not None and ws_id != last_id:
            last_id = ws_id
            print(f"desktop_watcher: workspace -> {ws_name}", flush=True)
            notify_island(ws_id, ws_name)

        time.sleep(POLL_INTERVAL)


# ============================================================
# MAIN
# ============================================================

def main():
    # Prefer Hyprland event socket if available.
    if shutil.which("hyprctl"):
        if run_hyprland_watcher():
            return

    # Fall back to generic polling.
    run_polling_watcher()


if __name__ == "__main__":
    main()
