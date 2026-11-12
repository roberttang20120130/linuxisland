# LinuxIsland

A modern, animated status bar and desktop overlay for Linux.

LinuxIsland provides a compact, dynamic interface for system information, notifications, and application integrations.


## Table of Contents

- [Features](#features)
- [Philosophy](#philosophy)
- [Requirements](#requirements)
  - [Python Standard Library](#python-standard-library)
  - [External Python Dependencies](#external-python-dependencies)
  - [System Libraries](#system-libraries)
- [Installation](#installation)
- [App Dock (v1.4.0)](#app-dock-v140)
- [Starting LinuxIsland](#starting-linuxisland)
- [Running](#running)
- [Architecture](#architecture)
  - [Watchers](#watchers)
  - [Main Application](#main-application)
- [HTTP API](#http-api)
  - [Event Endpoint](#event-endpoint)
  - [Generic Event Fields](#generic-event-fields)
  - [Example Request](#example-request)
  - [Specialized Events](#specialized-events)
  - [API Responses](#api-responses)
- [Integrations](#integrations)
- [Development](#development)
- [Security](#security)
- [License](#license)


## Features

- Animated compact and expanded states.
- System information display.
- Battery and charging notifications.
- Volume and Wi-Fi events.
- USB connection notifications.
- Temperature monitoring integrations.
- App dock: expand the island into a searchable, launchable app grid (v1.4.0).
- Local HTTP API for external integrations.
- GTK-based rendering.
- Wayland layer-shell integration.

## Philosophy

LinuxIsland separates monitoring from presentation.

**Watchers know. LinuxIsland shows.**

Individual watcher scripts monitor system events and communicate with the main application through its HTTP API. LinuxIsland focuses on displaying those events.

This keeps the monitoring logic independent of the presentation layer and makes integrations possible from virtually any programming language.

## Requirements

LinuxIsland uses:

### Python standard library

The following modules are included with Python and require no separate installation:

- `json`
- `os`
- `time`
- `http.client`
- `glob`
- `urllib.request`
- `subprocess`
- `threading`
- `datetime`
- `http.server`
- `re`

### External Python dependencies

- **PyGObject** (`gi`) — GTK and GLib integration.
- **Pycairo** (`cairo`) — Cairo rendering.
- **PyUDev** (`pyudev`) — device monitoring.

### System libraries

- GTK 3
- GTK Layer Shell
- GObject Introspection
- Cairo

LinuxIsland is designed for Wayland environments with GTK Layer Shell support.

## Installation

Clone the repository:

```bash
git clone https://github.com/roberttang20120130/linuxisland
cd linuxisland
```

Run the quick setup script:

```bash
chmod +x quicksetup.sh
./quicksetup.sh
```

If you do not want to install FIGlet, or FIGlet cannot be installed in your environment, use bare mode:

```bash
chmod +x quicksetup.sh
./quicksetup.sh --bare
```


The script detects supported package managers and installs the required dependencies.

Currently supported package managers:

- APT
- Pacman
- DNF

If your distribution does not support one of these package managers, install the listed dependencies using your distribution's native package manager. Make sure the Python packages are available to your system-managed Python installation

### Starting LinuxIsland

The setup script automatically configures startup after installing dependencies:

- **Hyprland** (preferred): Adds `exec-once` entries to `~/.config/hypr/hyprland.conf`.
- **systemd**: Creates and enables per-watcher user services in `~/.config/systemd/user/`.
- **Shell profile** (fallback): Appends a startup block to `~/.profile` or `~/.bashrc`.

You can also launch manually at any time:

```bash
python3 dynamic_island.py
```

### Managing Modules

Use the config CLI to enable, disable, or toggle individual watchers and sync them to your autostart method:

```bash
./config.sh status              # Show all modules and their state
./config.sh disable wifi        # Disable a watcher + remove from autostart
./config.sh toggle desktop_watcher  # Toggle on/off
./config.sh enable-all          # Enable everything
./config.sh sync                # Re-apply config to startup method
```

Settings persist in `~/.config/linuxisland/config.json`.

## App Dock (v1.4.0)

The island can expand into a full app dock: date header, live search bar, an "OPEN NOW" row of open windows, and a numbered grid of up to 16 apps (4 columns). The window resizes itself to fit the current match count as you type.

- **Trigger:** `Super+Space` — quicksetup adds this Hyprland keybind automatically on install.
- **While open:** typing filters the list live; arrows move the selection (wraps); Enter launches and auto-closes; Escape closes. The dock grabs the keyboard exclusively while open, so nothing leaks to your desktop.
- **CLI** (`island`, installed by quicksetup):

```bash
island                 # toggle dock open/closed
island search <term>   # filter the list live (auto-opens)
island launch <n|name> # launch Nth visible app, or match by name
island close           # same as toggle when open
```

### Dock HTTP events

All POST JSON to `http://127.0.0.1:8765/event`:

| type | fields | effect |
|---|---|---|
| `dock_toggle` | — | expand/collapse the dock |
| `dock_search` | `query` | set search filter (auto-opens) |
| `dock_launch` | `target` (number or name) | launch app from filtered list |

### Notes and limitations

- The dock is keyboard/CLI-driven. Some Hyprland builds do not deliver mouse clicks to layer-shell surfaces, so there is no click-to-launch.
- App entries show letter circles + number badges; icons are intentionally not rendered.
- Search matching is substring, case-insensitive, with no ranking.

## Running

Start the main application:

```bash
python3 dynamic_island.py
```

Watcher scripts are located alongside the main application.

## Architecture

LinuxIsland uses a watcher-based architecture.

Individual Python helper scripts monitor specific system events and send relevant information to the main application.

### Watchers

| Script | Responsibility |
|---|---|
| `battery_warn.py` | Battery warnings |
| `charging_watcher.py` | Charging status |
| `desktop_watcher.py` | Desktop / workspace switch notifications |
| `notification.py` | Notifications |
| `temprature.py` | Temperature monitoring |
| `usb_watcher.py` | USB connection events |
| `volume_watcher.py` | Volume monitoring |
| `wifi.py` | Wi-Fi monitoring |

### Main application

The main LinuxIsland application handles:

- Receiving events.
- Managing presentation state.
- Rendering the interface.
- Animations and transitions.
- Displaying information and notifications.

The watcher scripts and presentation layer are deliberately separated.

## HTTP API

LinuxIsland exposes a local HTTP API:

```text
http://127.0.0.1:8765
```

### Event endpoint

```http
POST /event
```

The API accepts JSON event data.

### Generic event fields

| Field | Required | Description |
|---|---|---|
| `type` | Yes | Event type (any string; `volume` and `charging` get special rendering) |
| `title` | No | Event title shown in bold. Defaults to the `type` value. |
| `value` | No | Right-aligned text next to the title. |
| `icon` | No | Leading symbol/emoji rendered before the title (e.g. `"🚀"`). |
| `progress` | No | Progress bar fill, 0–1 or 0–100. Renders a horizontal bar below the title. |
| `bar_color` | No | Hex colour for the progress bar fill (default white). E.g. `"#4FC3F7"`. |
| `border` | No | Border colour as hex string, e.g. `"#FF9500"`. |
| `border_width` | No | Border stroke width in pixels (default 2). |
| `border_radius` | No | Corner radius for the border (default matches island corners). |
| `duration` | No | Display duration in seconds (default 3). Minimum 0.1. |

All fields except `type` are optional. Events without new fields render exactly as before.

### Example request

```python
import json
import urllib.request

event = {
    "type": "generic",
    "title": "LinuxIsland",
    "value": "Hello from an external application!",
    "border": "#ffffff",
    "duration": 3
}

request = urllib.request.Request(
    "http://127.0.0.1:8765/event",
    data=json.dumps(event).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)

urllib.request.urlopen(request)
```

Any application capable of making HTTP requests can integrate with LinuxIsland.

### Example: event with icon and progress bar

```python
event = {
    "type": "download",
    "title": "Downloading",
    "value": "72%",
    "icon": "⬇️",
    "progress": 0.72,
    "bar_color": "#4FC3F7",
    "border": "#4FC3F7",
    "duration": 5
}
```

This renders a leading download emoji, the title and percentage, plus a horizontal progress bar filled to 72% in light blue.

### Specialized events

LinuxIsland also supports specialized event types, including:

- `volume` — uses the `volume` field. Renders a volume bar with percentage.
- `charging` — uses the `battery` field. Shows charging status with green border.
- `dock_toggle`, `dock_search` (`query`), `dock_launch` (`target`) — app dock controls (see [App Dock](#app-dock-v140)).
- Any other type renders as a generic event (title + value + optional icon/progress/border).

### API responses

Successful requests return:

```json
{"ok": true}
```

Invalid requests return HTTP 400.

Unknown paths return HTTP 404.

## Integrations

LinuxIsland is designed to be extensible.

Applications and scripts can communicate with it through the HTTP API without needing to use Python, GTK, or Cairo themselves.

This allows integrations to be written in practically any language that supports HTTP requests.

## Security

LinuxIsland's HTTP API listens on `127.0.0.1` and is intended
for local integrations.

It is not designed to be exposed directly to external networks.

## Development

LinuxIsland is intended to remain open to modification and extension.

Contributions, integrations, improvements, and forks are welcome.

if you want to contact the developer, email me at roberttang20120130@proton.me

## License

LinuxIsland is licensed under the **GNU General Public License v3.0 or later (GPL-3.0-or-later)**.

You are free to:

- Use LinuxIsland.
- Modify its source code.
- Redistribute it.
- Use it commercially.
- Create and distribute forks.

Distributed derivative works must comply with the GPL license.
