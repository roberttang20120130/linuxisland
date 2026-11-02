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

The setup script installs dependencies only. It does not automatically launch LinuxIsland or its watcher processes.

If your distribution does not support one of these package managers, install the listed dependencies using your distribution's native package manager. Make sure the Python packages are available to your system-managed Python installation

### Starting LinuxIsland

After running the setup script, choose one of the following methods to start LinuxIsland:

- **Hyprland:** Add an `exec-once` entry per script to your Hyprland configuration to launch LinuxIsland automatically when you log in.
- **systemd:** Create and enable a systemd *user service* to launch LinuxIsland automatically when your user session starts.

Alternatively, you can launch it manually once using:

```bash
python3 dynamic_island.py
```

The setup script does not configure automatic startup.

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

| Field | Description |
|---|---|
| `type` | Event type |
| `title` | Event title |
| `value` | Event content |
| `border` | Border colour |
| `border_width` | Border width |
| `border_radius` | Border radius |
| `duration` | Display duration |

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

### Specialized events

LinuxIsland also supports specialized event types, including:

- `volume` — uses the `volume` field.
- `charging` — uses the `battery` field.

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
