#!/usr/bin/env python3

import cairo
import glob as _glob_module
import gi
import json
import os
import shlex as _shlex_module
import subprocess
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
gi.require_version("PangoCairo", "1.0")

from gi.repository import (
    Gtk,
    Gdk,
    GLib,
    Pango,
    PangoCairo,
    GtkLayerShell,
)


# ============================================================
# CONFIG
# ============================================================

PORT = 8765

WINDOW_WIDTH = 390
WINDOW_HEIGHT = 460

NORMAL_WIDTH = 250
NORMAL_HEIGHT = 28

EXPANDED_WIDTH = 390
EXPANDED_HEIGHT = 92

# Shorter height for single-line events (no progress bar).
COMPACT_EXPANDED_HEIGHT = 48

# Animation only runs while expanding/collapsing.
ANIMATION_INTERVAL = 25
ANIMATION_SPEED = 0.24

# Slow system polling.
BATTERY_INFO_INTERVAL = 15
WIFI_INFO_INTERVAL = 10

VOLUME_DISPLAY_TIME = 3.0
CHARGING_DISPLAY_TIME = 2.0

CORNER_RADIUS = 16


# ============================================================
# BATTERY
# ============================================================

def get_battery():
    for name in ("BAT0", "BATT"):
        base = f"/sys/class/power_supply/{name}"

        capacity_file = os.path.join(base, "capacity")
        status_file = os.path.join(base, "status")

        if not os.path.exists(capacity_file):
            continue

        try:
            with open(capacity_file, "r", encoding="utf-8") as f:
                percent = int(f.read().strip())

            charging = False

            if os.path.exists(status_file):
                with open(status_file, "r", encoding="utf-8") as f:
                    charging = f.read().strip().lower() in (
                        "charging",
                        "full",
                    )

            if charging:
                icon = "⚡"
            elif percent <= 15:
                icon = "🪫"
            else:
                icon = "🔋"

            return icon, percent

        except (OSError, ValueError):
            pass

    return "🔋", None


# ============================================================
# WIFI
# ============================================================

def get_wifi():
    try:
        result = subprocess.run(
            [
                "nmcli",
                "-t",
                "-f",
                "ACTIVE,SSID,SIGNAL",
                "dev",
                "wifi",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )

        for line in result.stdout.splitlines():
            parts = line.split(":", 2)

            if len(parts) != 3:
                continue

            active, ssid, signal = parts

            if active != "yes":
                continue

            try:
                signal = int(signal)
            except ValueError:
                signal = None

            return "📶", ssid or "Wi-Fi", signal

    except (OSError, subprocess.SubprocessError):
        pass

    return "📡", "Disconnected", None


# ============================================================
# MONITOR
# ============================================================

def get_monitor():
    display = Gdk.Display.get_default()

    if display is None:
        return None

    monitor = display.get_primary_monitor()

    if monitor is None and display.get_n_monitors() > 0:
        monitor = display.get_monitor(0)

    return monitor


# ============================================================
# DYNAMIC ISLAND
# ============================================================

class DynamicIsland(Gtk.Window):

    def __init__(self):
        super().__init__()

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_app_paintable(True)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()

        if visual:
            self.set_visual(visual)

        self.set_default_size(
            WINDOW_WIDTH,
            WINDOW_HEIGHT,
        )

        self.resize(
            WINDOW_WIDTH,
            WINDOW_HEIGHT,
        )

        GtkLayerShell.init_for_window(self)

        GtkLayerShell.set_layer(
            self,
            GtkLayerShell.Layer.OVERLAY,
        )

        GtkLayerShell.set_anchor(
            self,
            GtkLayerShell.Edge.TOP,
            True,
        )

        GtkLayerShell.set_anchor(
            self,
            GtkLayerShell.Edge.LEFT,
            True,
        )

        GtkLayerShell.set_exclusive_zone(
            self,
            -1,
        )

        GtkLayerShell.set_keyboard_mode(
            self,
            GtkLayerShell.KeyboardMode.NONE,
        )

        # ----------------------------------------------------
        # DRAWING AREA
        # ----------------------------------------------------

        self.drawing_area = Gtk.DrawingArea()

        self.drawing_area.set_size_request(
            WINDOW_WIDTH,
            WINDOW_HEIGHT,
        )

        self.drawing_area.connect(
            "draw",
            self.on_draw,
        )

        self.add(self.drawing_area)

        # ----------------------------------------------------
        # ANIMATION STATE
        # ----------------------------------------------------

        self.visual_width = float(NORMAL_WIDTH)
        self.visual_height = float(NORMAL_HEIGHT)

        self.target_width = float(NORMAL_WIDTH)
        self.target_height = float(NORMAL_HEIGHT)

        # Actual layer-surface height (the window is resized on demand,
        # so this can differ from WINDOW_HEIGHT). Drawing must never be
        # clipped to the stale WINDOW_HEIGHT constant.
        self.surface_height = int(WINDOW_HEIGHT)

        self.animation_source_id = None

        # ----------------------------------------------------
        # PANGO CACHE
        # ----------------------------------------------------

        self.layout_cache = {}

        # ----------------------------------------------------
        # SYSTEM STATE
        # ----------------------------------------------------

        self.battery_icon = "🔋"
        self.battery_percent = None

        self.wifi_icon = "📡"
        self.wifi_ssid = "Disconnected"
        self.wifi_signal = None

        self.current_time = datetime.now().strftime("%H:%M")

        # ----------------------------------------------------
        # VOLUME EVENT
        # ----------------------------------------------------

        self.volume = None
        self.volume_active = False
        self.volume_timeout_id = None

        # ----------------------------------------------------
        # CHARGING EVENT
        # ----------------------------------------------------

        self.charging_battery = None
        self.charging_active = False
        self.charging_timeout_id = None

        # ----------------------------------------------------
        # GENERIC EVENT
        # ----------------------------------------------------

        self.generic_event = None
        self.generic_active = False
        self.generic_timeout_id = None

        # ----------------------------------------------------
        # DOCK STATE (BETA)
        # ----------------------------------------------------

        self.dock_active = False
        self.running_windows = []
        self.dock_search_query = ""
        self.dock_selected_index = 0

        # ----------------------------------------------------
        # INITIALIZATION
        # ----------------------------------------------------

        self.position_window()

        self.show_all()

        GLib.idle_add(
            self.enable_click_through
        )

        # BETA: keyboard toggle for the dock (Super+Space via hyprctl).
        # The island itself never receives focus; a tiny watcher thread
        # polls the active keybind state is too wasteful, so instead we
        # listen on the HTTP API: hyprland.conf binds Super+Space to
        # curl POST /event {"type":"dock_toggle"}.

        # BETA: typing goes to the search bar while the dock is open.
        self.connect("key-press-event", self.on_key_press)

        # Initial values.
        self.update_battery()
        self.update_wifi()

        # Clock updates itself at the next minute.
        self.schedule_clock_update()

        # Slow polling.
        GLib.timeout_add_seconds(
            BATTERY_INFO_INTERVAL,
            self.update_battery,
        )

        GLib.timeout_add_seconds(
            WIFI_INFO_INTERVAL,
            self.update_wifi,
        )

        self.queue_draw()

        print("Dynamic Island started.")

    # ========================================================
    # POSITION
    # ========================================================

    def position_window(self):
        monitor = get_monitor()

        if monitor is None:
            return

        geometry = monitor.get_geometry()

        left = (
            geometry.x
            + (geometry.width - WINDOW_WIDTH) // 2
        )

        GtkLayerShell.set_margin(
            self,
            GtkLayerShell.Edge.LEFT,
            left,
        )

        GtkLayerShell.set_margin(
            self,
            GtkLayerShell.Edge.TOP,
            0,
        )

    # ========================================================
    # CLICK THROUGH
    # ========================================================

    def enable_click_through(self):
        """Set the input shape so that ONLY a small region accepts clicks.

        Normal state: just the top 10px strip of the drawn pill.
        Dock open:    the whole dock panel area.

        Everything outside the region stays click-through, because this is
        a layer-shell surface and Hyprland hit-tests per pixel.
        """

        try:
            # Keep the window fully click-through (empty input region).
            # The dock is toggled by Super+Space, not by mouse clicks.
            empty_region = cairo.Region()

            gdk_window = self.get_window()

            if gdk_window is not None:
                gdk_window.input_shape_combine_region(
                    empty_region,
                    0,
                    0,
                )

        except Exception as error:
            print(
                "Dynamic Island: "
                "input-shape error:",
                repr(error),
            )

        return False

    # ========================================================
    # DOCK PANEL DRAWING (BETA)
    # ========================================================
    def set_dock_search(self, query):
        """Set the dock search filter (from HTTP / CLI)."""

        self.dock_search_query = str(query)

        if not self.dock_active:
            # Auto-open the dock when searching.
            self.refresh_running_windows()
            self._clear_all_events()
            self.dock_active = True
            self.dock_selected_index = 0

        self._update_dock_height()

        print(
            f"Dynamic Island [BETA]: search '{self.dock_search_query}'",
            flush=True,
        )

        self.queue_draw()

        return False

    def launch_dock_target(self, target):
        """Launch an app by its grid number or by name."""

        print(
            f"Dynamic Island [BETA]: launch target={target!r}",
            flush=True,
        )
        names = self._filtered_dock_apps()

        launched = None

        try:
            index = int(str(target)) - 1

            if 0 <= index < len(names):
                launched = names[index]
        except (TypeError, ValueError):
            # Not a number: match by name (case-insensitive substring).
            lowered = str(target).lower()

            for name in names:
                if lowered in name.lower():
                    launched = name
                    break

        if launched is None:
            print(
                f"Dynamic Island [BETA]: "
                f"no match for '{target}'",
                flush=True,
            )
            return False

        command = self._app_launch_command(launched)

        if command:
            try:
                print(
                    f"Dynamic Island [BETA]: cmd={command!r}",
                    flush=True,
                )
                err_file = open("/tmp/island_launch_err.log", "ab")
                subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=err_file,
                    start_new_session=True,
                )
                err_file.close()
                print(
                    f"Dynamic Island [BETA]: launched {launched}",
                    flush=True,
                )
            except OSError as error:
                print(
                    "Dynamic Island [BETA]: launch failed:",
                    repr(error),
                    flush=True,
                )

        return False

    def _app_launch_command(self, name):
        """Resolve an app display Name to its launch command.

        Only the FIRST [Desktop Entry] section is considered: desktop files
        contain extra sections (New Window / New Tab actions) whose Exec=
        lines would otherwise overwrite the real one.
        """

        try:
            paths = _glob_module.glob(
                "/usr/share/applications/*.desktop"
            )
            paths += _glob_module.glob(
                os.path.expanduser(
                    "~/.local/share/applications/*.desktop"
                )
            )
            # Snap apps live in a separate desktop directory.
            paths += _glob_module.glob(
                "/var/lib/snapd/desktop/applications/*.desktop"
            )
        except Exception:
            return None

        lowered = name.lower()

        for path in paths:
            display_name = None
            command = None
            in_first_section = False
            first_section_done = False

            try:
                with open(path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        stripped = line.strip()

                        if not stripped or stripped.startswith("#"):
                            continue

                        # Section headers.
                        if stripped.startswith("[") and stripped.endswith("]"):
                            if first_section_done:
                                break
                            in_first_section = (
                                stripped == "[Desktop Entry]"
                            )
                            if in_first_section:
                                first_section_done = True
                            continue

                        if not in_first_section:
                            continue

                        # Take the FIRST Name= / Exec= only.
                        if stripped.startswith("Name=") and display_name is None:
                            display_name = stripped[5:].strip()
                        elif stripped.startswith("Exec=") and command is None:
                            command = stripped[5:].strip()

            except OSError:
                continue

            if not display_name or display_name.lower() != lowered:
                continue

            if command:
                try:
                    clean = " ".join(
                        token
                        for token in _shlex_module.split(command)
                        if not token.startswith("%")
                    )
                    if clean:
                        # Use a shell so PATH lookup works for snap wrappers.
                        return ["sh", "-c", clean]
                except ValueError:
                    pass

        # Fallback: run the name as a plain command via the shell.
        return ["sh", "-c", name]

    def _filtered_dock_apps(self):
        """App names filtered by the current search query."""

        apps = self._dock_app_names()
        query = self.dock_search_query.strip().lower()

        if not query:
            return apps

        return [
            name for name in apps
            if query in name.lower()
        ]

    # ========================================================
    # DOCK VIEW DRAWING (BETA)
    # ========================================================

    def draw_dock_view(self, cr, x, y, width, height):
        """Draw the app-dock content INSIDE the expanded island body."""

        from datetime import datetime as _dt

        pad = 16

        # --- Date header (top center) ---
        today = _dt.now().strftime("%A, %d %B")
        self.draw_centered_text(
            cr, today, x + width / 2, y + 8, 14, True
        )

        # --- Search bar ---
        search_y = y + 30
        self.rounded_rectangle(
            cr, x + pad, search_y, width - pad * 2, 26, 10
        )
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.08)
        cr.fill()

        query = self.dock_search_query.strip()
        placeholder = (
            f"{query}  ({len(self._filtered_dock_apps())} matches)"
            if query
            else "island search <term>   island launch <n>"
        )

        self.draw_text(
            cr,
            f"🔍 {placeholder}",
            x + pad + 10,
            search_y + 7,
            10,
            False,
        )

        # --- Open-now row ---
        open_y = y + 64
        self.draw_text(cr, "OPEN NOW", x + pad, open_y, 9, True)

        chip_x = x + pad
        for title in self.running_windows[:3]:
            label = title[:16]
            est_w = max(72, len(label) * 6.5 + 18)
            if chip_x + est_w > x + width - pad:
                break

            self.rounded_rectangle(
                cr, chip_x, open_y + 14, est_w, 24, 12
            )
            cr.set_source_rgba(0.25, 0.85, 0.45, 0.25)
            cr.fill()

            self.draw_text(
                cr, label, chip_x + 9, open_y + 20, 10, False
            )
            chip_x += est_w + 6

        # --- App list (numbered, filtered by search, arrow-selectable) ---
        grid_top = y + 108
        cols = 4

        cell_w = (width - pad * 2 - (cols - 1) * 8) / cols

        names = self._filtered_dock_apps()[:16]

        for i, app_name in enumerate(names):
            row = i // cols
            col = i % cols

            cx = x + pad + col * (cell_w + 8)
            cy = grid_top + row * 74

            # Selection highlight.
            if i == self.dock_selected_index:
                self.rounded_rectangle(
                    cr, cx - 2, cy - 2, cell_w + 4, 70, 10
                )
                cr.set_source_rgba(0.35, 0.55, 1.0, 0.35)
                cr.fill()

            # Letter circle (no icons).
            cr.arc(cx + cell_w / 2, cy + 22, 18, 0, 3.14159)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.10)
            cr.fill()

            initial = (app_name[:1] or "?").upper()
            self.draw_centered_text(
                cr, initial, cx + cell_w / 2, cy + 14, 16, True
            )

            # Small launch number badge in the corner.
            self.draw_right_text(
                cr, str(i + 1),
                cx + cell_w - 3, cy + 2, 8, False
            )

            short = app_name if len(app_name) <= 12 else app_name[:11] + "…"
            self.draw_centered_text(
                cr, short, cx + cell_w / 2, cy + 46, 9, False
            )

        # --- Footer hint ---
        self.draw_centered_text(
            cr, "↑↓ select · Enter launch · Esc close",
            x + width / 2, y + height - 18, 9, False
        )

        return False

    def _dock_app_names(self):
        """Cached list of installed app names (parsed once per session)."""

        if getattr(self, "_dock_apps_cache", None) is None:
            import glob as _g
            
            apps = []
            seen = set()

            try:
                paths = _g.glob("/usr/share/applications/*.desktop")
                paths += _g.glob(
                    os.path.expanduser(
                        "~/.local/share/applications/*.desktop"
                    )
                )
                # Snap apps live in a separate desktop directory.
                paths += _g.glob(
                    "/var/lib/snapd/desktop/applications/*.desktop"
                )
            except Exception:
                paths = []

            for path in sorted(paths):
                name = None
                no_display = False

                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        for line in handle:
                            line = line.strip()
                            # Take the FIRST Name= only (desktop files can
                            # contain extra localized/alt name lines).
                            if line.startswith("Name=") and name is None:
                                name = line[5:].strip()
                            elif line.lower().startswith("nodisplay"):
                                no_display = True
                except OSError:
                    continue

                if not name or no_display:
                    continue

                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                apps.append(name)

            self._dock_apps_cache = apps

        return self._dock_apps_cache

    # ========================================================
    # DOCK TOGGLE (BETA) — Super+Space via HTTP event
    # ========================================================

    DOCK_EXPANDED_HEIGHT = 340

    def toggle_dock(self):
        """Expand/collapse the island into the app-dock view."""

        if self.dock_active:
            # Closing: release the keyboard. The input shape is handed
            # back to "pill only" by the collapse animation (see
            # animation_tick), so no separate empty-shape call here —
            # that would leave a tall, fully click-through surface until
            # the next event.
            GtkLayerShell.set_keyboard_mode(
                self,
                GtkLayerShell.KeyboardMode.NONE,
            )
            self.dock_active = False
            self.collapse()
        else:
            # Opening: intercept mouse + take the keyboard while open.
            self._set_input_shape_full()
            GtkLayerShell.set_keyboard_mode(
                self,
                GtkLayerShell.KeyboardMode.EXCLUSIVE,
            )
            self.refresh_running_windows()
            self._clear_all_events()
            self.dock_active = True
            self.expand(self.DOCK_EXPANDED_HEIGHT)

        print(
            f"Dynamic Island [BETA]: dock "
            f"{'opened' if self.dock_active else 'closed'}",
            flush=True,
        )

        self.queue_draw()

        return False

    def _set_input_shape_empty(self):
        """No clickable area: fully click-through (closed state)."""

        try:
            region = cairo.Region()
            gdk_window = self.get_window()

            if gdk_window is not None:
                gdk_window.input_shape_combine_region(
                    region, 0, 0
                )
        except Exception as error:
            print("input-shape (empty) error:", repr(error), flush=True)

    def _set_input_shape_full(self):
        """Whole window clickable while the dock is open.

        Layer-shell surfaces are hit-tested per pixel on their drawn
        content, so we simply do NOT restrict the input shape: every
        opaque/drawn pixel of the expanded panel receives clicks.
        (An empty cairo.Region cannot express a rectangle in pycairo,
        and restricting it is what broke clicks before.)
        """

        try:
            gdk_window = self.get_window()

            if gdk_window is not None:
                # Clear any previous restriction by combining the full
                # window area. We build that region from the window's own
                # size using a cairo surface-backed mask is overkill; the
                # simplest correct move on Wayland layer surfaces is to
                # leave input shape unset, which means "use drawn pixels".
                pass
        except Exception as error:
            print("input-shape (full) error:", repr(error), flush=True)

    def _set_input_shape_pill(self):
        """Input region = the currently drawn pill only.

        Keeps every pixel outside the visible island fully click-through
        even while the window surface is tall (expanded dock). The input
        shape must be re-applied whenever the animated size changes, so
        it is refreshed from animation_tick().
        """

        try:
            region = cairo.Region()

            # Round to whole pixels; a zero-size pill means "empty".
            w = int(self.visual_width)
            h = int(self.visual_height)

            if w > 0 and h > 0:
                # RectangleInt requires integers; the pill x-offset is a
                # float (the window is wider than the drawn pill).
                x = int((WINDOW_WIDTH - self.visual_width) / 2.0)
                region.union(cairo.RectangleInt(x, 0, w, h))

            gdk_window = self.get_window()

            if gdk_window is not None:
                gdk_window.input_shape_combine_region(
                    region,
                    0,
                    0,
                )

        except Exception as error:
            print("input-shape (pill) error:", repr(error), flush=True)

    def on_key_press(self, widget, event):
        """Typing while the dock is open goes to the search bar."""

        if not self.dock_active:
            return False

        keyval = event.keyval

        # Escape closes the dock.
        if keyval == Gdk.KEY_Escape:
            GLib.idle_add(self.toggle_dock)
            return True

        # Backspace deletes the last character.
        if keyval == Gdk.KEY_BackSpace:
            self.dock_search_query = self.dock_search_query[:-1]
            self.dock_selected_index = 0
            self._update_dock_height()
            self.queue_draw()
            return True

        # Enter launches the highlighted app.
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            names = self._filtered_dock_apps()[:16]

            print(
                f"Dynamic Island [BETA]: ENTER pressed, "
                f"selected={self.dock_selected_index}, "
                f"matches={len(names)}",
                flush=True,
            )

            if 0 <= self.dock_selected_index < len(names):
                app_name = names[self.dock_selected_index]
                print(
                    f"Dynamic Island [BETA]: launching "
                    f"'{app_name}'",
                    flush=True,
                )
                GLib.idle_add(
                    self.launch_dock_target,
                    app_name,
                )
                # Close after launching.
                GLib.timeout_add(250, lambda: (self.toggle_dock(), False)[1])

            return True

        # Arrow keys move the selection. The index is clamped first so a
        # stale out-of-range value can never wrap to the wrong end of the
        # list (e.g. index 15 with 3 matches would jump to match 2).
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Right,
                      Gdk.KEY_Up, Gdk.KEY_Left):
            names = self._filtered_dock_apps()[:16]

            if not names:
                return True

            step = 1 if keyval in (Gdk.KEY_Down, Gdk.KEY_Right) else -1

            index = min(
                max(self.dock_selected_index, 0),
                len(names) - 1,
            )

            self.dock_selected_index = (index + step) % len(names)

            self.queue_draw()
            return True

        # Printable ASCII appends to the query.
        if 32 <= keyval < 127:
            self.dock_search_query += chr(keyval)
            self.dock_selected_index = 0
            self._update_dock_height()
            self.queue_draw()
            return True

        return False

    def _update_dock_height(self):
        """Grow/shrink the island to fit the current match count."""

        names = self._filtered_dock_apps()[:16]
        rows = max(1, (len(names) + 3) // 4)

        # Base layout: date(28) + search(30+8) + open-now(38+8) + grid.
        height = 150 + rows * 74 + 24

        self.target_height = float(height)

        # Clamp the selection: filters can shrink the visible list below
        # the current index (e.g. typing a query with one match while an
        # earlier item was highlighted).
        if not names or self.dock_selected_index >= len(names):
            self.dock_selected_index = 0

        # Resize the layer surface immediately so content is never drawn
        # past the bottom edge of a too-small window mid-animation.
        self._sync_surface_height(max(self.surface_height, height))

        self.start_animation()

    def refresh_running_windows(self):
        """One-shot list of open window titles via hyprctl."""

        try:
            result = subprocess.run(
                ["hyprctl", "clients"],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            self.running_windows = []
            return

        windows = []

        for line in result.stdout.splitlines():
            if not line.startswith("Window ") or "->" not in line:
                continue

            parts = line.split("->", 1)

            if len(parts) == 2:
                title = parts[1].strip()
                windows.append(title[:48])

        self.running_windows = windows[:6]

    # ========================================================
    # BATTERY UPDATE
    # ========================================================

    def update_battery(self):
        old_state = (
            self.battery_icon,
            self.battery_percent,
        )

        (
            self.battery_icon,
            self.battery_percent,
        ) = get_battery()

        new_state = (
            self.battery_icon,
            self.battery_percent,
        )

        if new_state != old_state:
            self.queue_draw()

        return True

    # ========================================================
    # WIFI UPDATE
    # ========================================================

    def update_wifi(self):
        old_state = (
            self.wifi_icon,
            self.wifi_ssid,
            self.wifi_signal,
        )

        (
            self.wifi_icon,
            self.wifi_ssid,
            self.wifi_signal,
        ) = get_wifi()

        new_state = (
            self.wifi_icon,
            self.wifi_ssid,
            self.wifi_signal,
        )

        if new_state != old_state:
            self.queue_draw()

        return True

    # ========================================================
    # CLOCK
    # ========================================================

    def schedule_clock_update(self):
        now = datetime.now()

        seconds_until_next_minute = (
            60
            - now.second
            - now.microsecond / 1_000_000
        )

        delay_ms = max(
            100,
            int(seconds_until_next_minute * 1000),
        )

        GLib.timeout_add(
            delay_ms,
            self.update_clock,
        )

    def update_clock(self):
        new_time = datetime.now().strftime("%H:%M")

        if new_time != self.current_time:
            self.current_time = new_time
            self.queue_draw()

        self.schedule_clock_update()

        return False

    # ========================================================
    # PANGO CACHE
    # ========================================================

    def get_text_layout(
        self,
        text,
        size,
        bold,
    ):
        key = (
            str(text),
            int(size),
            bool(bold),
        )

        layout = self.layout_cache.get(key)

        if layout is not None:
            return layout

        layout = self.create_pango_layout(
            str(text)
        )

        font = (
            f"Sans Bold {size}"
            if bold
            else f"Sans {size}"
        )

        layout.set_font_description(
            Pango.FontDescription(font)
        )

        self.layout_cache[key] = layout

        # Don't allow arbitrary event strings
        # to grow the cache forever.
        if len(self.layout_cache) > 64:
            oldest_key = next(
                iter(self.layout_cache)
            )
            del self.layout_cache[oldest_key]

        return layout

    # ========================================================
    # TEXT DRAWING
    # ========================================================

    def draw_text(
        self,
        cr,
        text,
        x,
        y,
        size,
        bold=False,
    ):
        layout = self.get_text_layout(
            text,
            size,
            bold,
        )

        cr.set_source_rgba(
            1.0,
            1.0,
            1.0,
            1.0,
        )

        cr.move_to(x, y)

        PangoCairo.show_layout(
            cr,
            layout,
        )

        return layout

    def draw_centered_text(
        self,
        cr,
        text,
        center_x,
        y,
        size,
        bold=False,
    ):
        layout = self.get_text_layout(
            text,
            size,
            bold,
        )

        text_width, _ = layout.get_pixel_size()

        cr.set_source_rgba(
            1.0,
            1.0,
            1.0,
            1.0,
        )

        cr.move_to(
            center_x - text_width / 2,
            y,
        )

        PangoCairo.show_layout(
            cr,
            layout,
        )

    def draw_right_text(
        self,
        cr,
        text,
        right_x,
        y,
        size,
        bold=False,
    ):
        layout = self.get_text_layout(
            text,
            size,
            bold,
        )

        text_width, _ = layout.get_pixel_size()

        cr.set_source_rgba(
            1.0,
            1.0,
            1.0,
            1.0,
        )

        cr.move_to(
            right_x - text_width,
            y,
        )

        PangoCairo.show_layout(
            cr,
            layout,
        )

    # ========================================================
    # ROUNDED RECTANGLE
    # ========================================================

    def rounded_rectangle(
        self,
        cr,
        x,
        y,
        width,
        height,
        radius,
    ):
        radius = min(
            radius,
            width / 2,
            height / 2,
        )

        pi = 3.141592653589793

        cr.new_path()

        # Top-left corner is SQUARE.
        cr.move_to(
            x,
            y,
        )

        # Straight top edge.
        cr.line_to(
            x + width,
            y,
        )

        # Straight right edge down to
        # the beginning of the bottom-right curve.
        cr.line_to(
            x + width,
            y + height - radius,
        )

        # Bottom-right rounded corner.
        cr.arc(
            x + width - radius,
            y + height - radius,
            radius,
            0,
            0.5 * pi,
        )

        # Straight bottom edge.
        cr.line_to(
            x + radius,
            y + height,
        )

        # Bottom-left rounded corner.
        cr.arc(
            x + radius,
            y + height - radius,
            radius,
            0.5 * pi,
            pi,
        )

        # Straight left edge.
        cr.line_to(
            x,
            y,
        )

        cr.close_path()

    # ========================================================
    # DRAW
    # ========================================================

    def on_draw(
        self,
        widget,
        cr,
    ):
        # Clear transparent background.
        cr.set_operator(
            cairo.OPERATOR_SOURCE
        )

        cr.set_source_rgba(
            0,
            0,
            0,
            0,
        )

        cr.paint()

        cr.set_operator(
            cairo.OPERATOR_OVER
        )

        width = min(
            self.visual_width,
            WINDOW_WIDTH,
        )

        # Never clip the drawing to the stale WINDOW_HEIGHT constant —
        # the layer surface is resized on demand (see _sync_surface_height)
        # and can legitimately be taller than the initial value.
        height = min(
            self.visual_height,
            float(self.surface_height),
        )

        if width <= 0 or height <= 0:
            return False

        x = (
            WINDOW_WIDTH - width
        ) / 2

        y = 0

        # ----------------------------------------------------
        # BACKGROUND
        # ----------------------------------------------------

        cr.set_source_rgba(
            0.0,
            0.0,
            0.0,
            1.0,
        )

        self.rounded_rectangle(
            cr,
            x,
            y,
            width,
            height,
            CORNER_RADIUS,
        )

        cr.fill()

        # ----------------------------------------------------
        # CHARGING BORDER
        # ----------------------------------------------------

        if self.charging_active:

            cr.set_source_rgba(
                0.1,
                1.0,
                0.25,
                1.0,
            )

            cr.set_line_width(2.0)

            inset = 1.0

            self.rounded_rectangle(
                cr,
                x + inset,
                y + inset,
                width - inset * 2,
                height - inset * 2,
                CORNER_RADIUS,
            )

            cr.stroke()

        # ----------------------------------------------------
        # GENERIC BORDER
        # ----------------------------------------------------

        if self.generic_active:

            event = self.generic_event or {}

            border = event.get(
                "border"
            )

            if border:

                try:
                    color = str(
                        border
                    ).lstrip("#")

                    if len(color) == 3:
                        color = "".join(
                            c + c
                            for c in color
                        )

                    if len(color) == 6:

                        r = int(
                            color[0:2],
                            16,
                        ) / 255.0

                        g = int(
                            color[2:4],
                            16,
                        ) / 255.0

                        b = int(
                            color[4:6],
                            16,
                        ) / 255.0

                        border_width = max(
                            0.1,
                            float(
                                event.get(
                                    "border_width",
                                    2,
                                )
                            ),
                        )

                        border_radius = max(
                            0,
                            float(
                                event.get(
                                    "border_radius",
                                    CORNER_RADIUS + 1,
                                )
                            ),
                        )

                        cr.set_source_rgba(
                            r,
                            g,
                            b,
                            1.0,
                        )

                        cr.set_line_width(
                            border_width
                        )

                        inset = (
                            border_width / 2
                        )

                        self.rounded_rectangle(
                            cr,
                            x + inset,
                            y + inset,
                            width - inset * 2,
                            height - inset * 2,
                            border_radius,
                        )

                        cr.stroke()

                except (
                    TypeError,
                    ValueError,
                ):
                    pass

        if height < 15:
            return False

        # ----------------------------------------------------
        # CHARGING VIEW
        # ----------------------------------------------------

        if self.charging_active:

            battery = (
                self.charging_battery
                if self.charging_battery is not None
                else 0
            )

            battery = max(
                0,
                min(
                    100,
                    int(battery),
                ),
            )

            self.draw_text(
                cr,
                "⚡  CHARGING",
                x + 18,
                13,
                16,
                True,
            )

            self.draw_right_text(
                cr,
                f"{battery}%",
                x + width - 18,
                13,
                16,
                True,
            )

            return False

        # ----------------------------------------------------
        # VOLUME VIEW
        # ----------------------------------------------------

        if self.volume_active:

            volume = (
                self.volume
                if self.volume is not None
                else 0
            )

            volume = max(
                0,
                min(
                    100,
                    int(volume),
                ),
            )

            self.draw_text(
                cr,
                "🔊  Volume",
                x + 18,
                13,
                16,
                True,
            )

            self.draw_right_text(
                cr,
                f"{volume}%",
                x + width - 18,
                13,
                16,
                True,
            )

            bar_x = x + 18
            bar_y = 50
            bar_width = width - 36
            bar_height = 10
            bar_radius = bar_height / 2

            cr.set_source_rgba(
                0.18,
                0.18,
                0.20,
                1.0,
            )

            self.rounded_rectangle(
                cr,
                bar_x,
                bar_y,
                bar_width,
                bar_height,
                bar_radius,
            )

            cr.fill()

            if volume > 0:

                fill_width = (
                    bar_width
                    * volume
                    / 100
                )

                fill_width = max(
                    bar_height,
                    fill_width,
                )

                fill_width = min(
                    bar_width,
                    fill_width,
                )

                cr.set_source_rgba(
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                )

                self.rounded_rectangle(
                    cr,
                    bar_x,
                    bar_y,
                    fill_width,
                    bar_height,
                    bar_radius,
                )

                cr.fill()

            return False

        # ----------------------------------------------------
        # GENERIC EVENT VIEW
        # ----------------------------------------------------

        if self.generic_active:

            event = (
                self.generic_event
                or {}
            )

            title = event.get(
                "title",
                event.get(
                    "type",
                    "Event",
                ),
            )

            value = event.get(
                "value",
                "",
            )

            icon = event.get(
                "icon",
                "",
            )

            # Optional leading symbol before the title.
            if icon:
                self.draw_text(
                    cr,
                    str(icon),
                    x + 12,
                    13,
                    16,
                    False,
                )

                title_x = x + 40
            else:
                title_x = x + 18

            self.draw_text(
                cr,
                title,
                title_x,
                13,
                16,
                True,
            )

            if value != "":
                self.draw_right_text(
                    cr,
                    value,
                    x + width - 18,
                    13,
                    16,
                    True,
                )

            # Optional progress bar.
            # Accepts "progress" as a number 0-100 or 0.0-1.0.
            progress = event.get("progress")

            if progress is not None:

                try:
                    progress_val = float(progress)
                except (TypeError, ValueError):
                    progress_val = None

                if progress_val is not None:

                    # Support both 0-1 and 0-100 ranges.
                    if progress_val <= 1.0:
                        progress_val *= 100.0

                    progress_val = max(
                        0.0,
                        min(100.0, progress_val),
                    )

                    bar_x = x + 18
                    bar_y = 50
                    bar_width = width - 36
                    bar_height = 10
                    bar_radius = bar_height / 2

                    # Optional custom bar colour from event.
                    bar_color = event.get("bar_color")
                    r, g, b = 1.0, 1.0, 1.0

                    if bar_color:
                        try:
                            color_str = str(bar_color).lstrip("#")
                            if len(color_str) == 3:
                                color_str = "".join(
                                    c + c for c in color_str
                                )
                            if len(color_str) == 6:
                                r = int(color_str[0:2], 16) / 255.0
                                g = int(color_str[2:4], 16) / 255.0
                                b = int(color_str[4:6], 16) / 255.0
                        except (TypeError, ValueError):
                            pass

                    # Background track.
                    cr.set_source_rgba(
                        0.18,
                        0.18,
                        0.20,
                        1.0,
                    )

                    self.rounded_rectangle(
                        cr,
                        bar_x,
                        bar_y,
                        bar_width,
                        bar_height,
                        bar_radius,
                    )

                    cr.fill()

                    # Filled portion.
                    if progress_val > 0:

                        fill_width = (
                            bar_width * progress_val / 100.0
                        )

                        fill_width = max(
                            bar_height,
                            fill_width,
                        )

                        fill_width = min(
                            bar_width,
                            fill_width,
                        )

                        cr.set_source_rgba(
                            r, g, b, 1.0,
                        )

                        self.rounded_rectangle(
                            cr,
                            bar_x,
                            bar_y,
                            fill_width,
                            bar_height,
                            bar_radius,
                        )

                        cr.fill()

            return False

        # ----------------------------------------------------
        # DOCK VIEW (BETA) — island expanded into the app dock.
        # ----------------------------------------------------

        if self.dock_active:
            return self.draw_dock_view(cr, x, y, width, height)

        # NORMAL VIEW
        # ----------------------------------------------------

        if self.battery_percent is None:
            battery_text = (
                f"{self.battery_icon} --"
            )
        else:
            battery_text = (
                f"{self.battery_icon} "
                f"{self.battery_percent}%"
            )

        if self.wifi_signal is None:
            wifi_text = (
                f"{self.wifi_icon} --"
            )
        else:
            wifi_text = (
                f"{self.wifi_icon} "
                f"{self.wifi_signal}%"
            )

        padding = 12

        self.draw_text(
            cr,
            battery_text,
            x + padding,
            5,
            10,
            False,
        )

        self.draw_centered_text(
            cr,
            self.current_time,
            x + width / 2,
            3,
            14,
            True,
        )

        self.draw_right_text(
            cr,
            wifi_text,
            x + width - padding,
            5,
            10,
            False,
        )

        return False

    # ========================================================
    # ANIMATION
    # ========================================================

    def _sync_surface_height(self, height):
        """Grow/shrink the actual layer surface so the drawing area can
        hold `height` pixels. Only resizes when needed (layer-shell
        resize requests are comparatively expensive)."""

        try:
            if int(height) != self.surface_height:
                new_h = max(NORMAL_HEIGHT, int(height))
                self.resize(WINDOW_WIDTH, new_h)
                self.surface_height = new_h
        except Exception as error:
            print("surface resize error:", repr(error), flush=True)

    def start_animation(self):

        if self.animation_source_id is not None:
            return

        # Already there? Don't create a timer.
        if (
            abs(
                self.visual_width
                - self.target_width
            ) < 0.25
            and
            abs(
                self.visual_height
                - self.target_height
            ) < 0.25
        ):
            self.visual_width = (
                self.target_width
            )

            self.visual_height = (
                self.target_height
            )

            return

        self.animation_source_id = (
            GLib.timeout_add(
                ANIMATION_INTERVAL,
                self.animation_tick,
            )
        )

    def expand(self, height=None):

        self.target_width = float(
            EXPANDED_WIDTH
        )

        if height is not None:
            self.target_height = float(height)
        else:
            self.target_height = float(EXPANDED_HEIGHT)

        self.start_animation()

    def collapse(self):

        self.target_width = float(
            NORMAL_WIDTH
        )

        self.target_height = float(
            NORMAL_HEIGHT
        )

        # Shrink the layer surface back to normal size. The animation
        # tick keeps it in sync while the visual pill collapses.
        self._sync_surface_height(WINDOW_HEIGHT)

        self.start_animation()

    def animation_tick(self):

        dw = (
            self.target_width
            - self.visual_width
        )

        dh = (
            self.target_height
            - self.visual_height
        )

        if abs(dw) < 0.25:
            self.visual_width = (
                self.target_width
            )
        else:
            self.visual_width += (
                dw * ANIMATION_SPEED
            )

        if abs(dh) < 0.25:
            self.visual_height = (
                self.target_height
            )
        else:
            self.visual_height += (
                dh * ANIMATION_SPEED
            )

        # Keep the layer surface in step with the animated size so the
        # dock is never clipped by a stale, smaller window.
        self._sync_surface_height(self.visual_height)

        # Keep the input shape hugging the drawn pill so the rest of the
        # (possibly tall) surface stays click-through during animation.
        if not self.dock_active:
            self._set_input_shape_pill()

        self.queue_draw()

        if (
            abs(
                self.target_width
                - self.visual_width
            ) < 0.25
            and
            abs(
                self.target_height
                - self.visual_height
            ) < 0.25
        ):
            self.visual_width = (
                self.target_width
            )

            self.visual_height = (
                self.target_height
            )

            self.animation_source_id = None

            return False

        return True

    # ========================================================
    # EVENT DISPLACEMENT
    # ========================================================

    def _clear_all_events(self):
        """Clear all active event states and their timeouts."""

        if self.volume_timeout_id is not None:
            try:
                GLib.source_remove(self.volume_timeout_id)
            except Exception:
                pass
            self.volume_timeout_id = None

        if self.charging_timeout_id is not None:
            try:
                GLib.source_remove(self.charging_timeout_id)
            except Exception:
                pass
            self.charging_timeout_id = None

        if self.generic_timeout_id is not None:
            try:
                GLib.source_remove(self.generic_timeout_id)
            except Exception:
                pass
            self.generic_timeout_id = None

        self.volume_active = False
        self.charging_active = False
        self.generic_active = False
        self.generic_event = None

    # ========================================================
    # VOLUME
    # ========================================================

    def show_volume(self, data):

        if self.charging_active:
            return False

        try:
            volume = int(
                data.get(
                    "volume",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            volume = 0

        self._clear_all_events()

        self.volume = max(
            0,
            min(
                100,
                volume,
            ),
        )

        self.volume_active = True

        self.expand()

        if self.volume_timeout_id is not None:
            try:
                GLib.source_remove(
                    self.volume_timeout_id
                )
            except Exception:
                pass

            self.volume_timeout_id = None

        self.volume_timeout_id = (
            GLib.timeout_add(
                int(
                    VOLUME_DISPLAY_TIME
                    * 1000
                ),
                self.finish_volume,
            )
        )

        self.queue_draw()

        return False

    def finish_volume(self):

        self.volume_timeout_id = None

        # Only collapse if no other event has taken over.
        if not (self.charging_active or self.generic_active):
            self.volume_active = False
            self.collapse()

        self.queue_draw()

        return False

    # ========================================================
    # CHARGING
    # ========================================================

    def show_charging(self, data):

        try:
            battery = int(
                data.get(
                    "battery",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            battery = 0

        self._clear_all_events()

        self.charging_battery = max(
            0,
            min(
                100,
                battery,
            ),
        )

        self.charging_active = True

        self.expand()

        if self.charging_timeout_id is not None:
            try:
                GLib.source_remove(
                    self.charging_timeout_id
                )
            except Exception:
                pass

            self.charging_timeout_id = None

        self.charging_timeout_id = (
            GLib.timeout_add(
                int(
                    CHARGING_DISPLAY_TIME
                    * 1000
                ),
                self.finish_charging,
            )
        )

        self.queue_draw()

        return False

    def finish_charging(self):

        self.charging_timeout_id = None

        # Only collapse if no other event has taken over.
        if not (self.volume_active or self.generic_active):
            self.charging_active = False
            self.collapse()

        self.queue_draw()

        return False

    # ========================================================
    # GENERIC EVENT
    # ========================================================

    def show_generic(self, data):

        self._clear_all_events()

        self.generic_event = data

        self.generic_active = True

        # Use compact height for single-line events (no progress bar).
        if "progress" in data:
            self.expand(EXPANDED_HEIGHT)
        else:
            self.expand(COMPACT_EXPANDED_HEIGHT)

        if self.generic_timeout_id is not None:
            try:
                GLib.source_remove(
                    self.generic_timeout_id
                )
            except Exception:
                pass

            self.generic_timeout_id = None

        try:
            duration = float(
                data.get(
                    "duration",
                    3,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            duration = 3.0

        duration = max(
            0.1,
            duration,
        )

        self.generic_timeout_id = (
            GLib.timeout_add(
                int(duration * 1000),
                self.finish_generic,
            )
        )

        self.queue_draw()

        return False

    def finish_generic(self):

        self.generic_timeout_id = None

        # Only collapse if no other event has taken over.
        if not (self.volume_active or self.charging_active):
            self.generic_active = False
            self.generic_event = None
            self.collapse()

        self.queue_draw()

        return False

    # ========================================================
    # CLOSE
    # ========================================================

    def close_island(self):

        source_ids = (
            self.animation_source_id,
            self.volume_timeout_id,
            self.charging_timeout_id,
            self.generic_timeout_id,
        )

        for source_id in source_ids:

            if source_id is not None:

                try:
                    GLib.source_remove(
                        source_id
                    )
                except Exception:
                    pass

        Gtk.main_quit()

        return False


# ============================================================
# HTTP API
# ============================================================

island = None


class EventHandler(BaseHTTPRequestHandler):

    def send_cors(self):

        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "POST, OPTIONS",
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )

    def do_OPTIONS(self):

        self.send_response(204)

        self.send_cors()

        self.end_headers()

    def do_POST(self):

        if self.path != "/event":

            self.send_response(404)

            self.send_cors()

            self.end_headers()

            return

        try:

            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )

            body = self.rfile.read(
                length
            )

            data = json.loads(
                body.decode("utf-8")
            )

            if not isinstance(
                data,
                dict,
            ):
                raise ValueError(
                    "Expected JSON object"
                )

            event_type = data.get(
                "type"
            )

            if not event_type:
                raise ValueError(
                    "Missing event type"
                )

            if event_type == "charging":

                GLib.idle_add(
                    island.show_charging,
                    data,
                )

            elif event_type == "volume":

                GLib.idle_add(
                    island.show_volume,
                    data,
                )

            elif event_type == "dock_toggle":

                # BETA: toggle the app-dock panel (Super+Space).
                GLib.idle_add(
                    island.toggle_dock,
                )

            elif event_type == "dock_search":

                # BETA: filter the dock grid by search query.
                query = data.get("query", "")

                GLib.idle_add(
                    island.set_dock_search,
                    str(query),
                )

            elif event_type == "dock_launch":

                # BETA: launch an app from the current filtered list.
                target = data.get("target")

                GLib.idle_add(
                    island.launch_dock_target,
                    target,
                )

            else:

                GLib.idle_add(
                    island.show_generic,
                    data,
                )

            self.send_response(200)

            self.send_cors()

            self.send_header(
                "Content-Type",
                "application/json",
            )

            self.end_headers()

            self.wfile.write(
                b'{"ok":true}\n'
            )

        except Exception as error:

            self.send_response(400)

            self.send_cors()

            self.send_header(
                "Content-Type",
                "application/json",
            )

            self.end_headers()

            self.wfile.write(
                json.dumps(
                    {
                        "ok": False,
                        "error": str(error),
                    }
                ).encode()
            )

    def log_message(
        self,
        format,
        *args,
    ):
        pass


# ============================================================
# SERVER
# ============================================================

def run_server():

    try:

        server = ThreadingHTTPServer(
            (
                "127.0.0.1",
                PORT,
            ),
            EventHandler,
        )

        print(
            "Dynamic Island HTTP server "
            f"listening on 127.0.0.1:{PORT}"
        )

        server.serve_forever()

    except OSError as error:

        if getattr(
            error,
            "errno",
            None,
        ) == 98:

            print(
                f"Dynamic Island HTTP server: "
                f"port {PORT} is already in use."
            )

            print(
                "Another Dynamic Island instance "
                "is probably running."
            )

        else:

            print(
                "Dynamic Island HTTP server error:",
                repr(error),
            )


# ============================================================
# MAIN
# ============================================================

def main():

    global island

    island = DynamicIsland()

    island.connect(
        "destroy",
        lambda *_: island.close_island(),
    )

    server_thread = threading.Thread(
        target=run_server,
        daemon=True,
    )

    server_thread.start()

    try:
        Gtk.main()
    finally:
        pass


if __name__ == "__main__":
    main()
