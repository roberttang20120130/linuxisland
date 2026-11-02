# LinuxIsland

A modern, animated status bar and desktop overlay for Linux.

LinuxIsland provides a compact, dynamic interface for system information, notifications, and application integrations.

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

The script detects supported package managers and installs the required dependencies.

Currently supported package managers:

- APT
- Pacman
- DNF

The setup script installs dependencies only. It does not automatically launch LinuxIsland or its watcher processes.

## Running

Start the main application:

```bash
python3 linuxisland.py
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

## Development

LinuxIsland is intended to remain open to modification and extension.

Contributions, integrations, improvements, and forks are welcome.

## License

LinuxIsland is licensed under the **GNU General Public License v3.0 or later (GPL-3.0-or-later)**.

You are free to:

- Use LinuxIsland.
- Modify its source code.
- Redistribute it.
- Use it commercially.
- Create and distribute forks.

Distributed derivative works must comply with the GPL license.
