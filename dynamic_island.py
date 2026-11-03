#!/usr/bin/env python3

import cairo
import gi
import json
import os
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
WINDOW_HEIGHT = 92

NORMAL_WIDTH = 250
NORMAL_HEIGHT = 28

EXPANDED_WIDTH = 390
EXPANDED_HEIGHT = 92

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
        # INITIALIZATION
        # ----------------------------------------------------

        self.position_window()

        self.show_all()

        GLib.idle_add(
            self.enable_click_through
        )

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
        try:
            empty_region = cairo.Region()

            self.input_shape_combine_region(
                empty_region
            )

            gdk_window = self.get_window()

            if gdk_window is not None:
                gdk_window.input_shape_combine_region(
                    empty_region,
                    0,
                    0,
                )

            print(
                "Dynamic Island: "
                "click-through enabled"
            )

        except Exception as error:
            print(
                "Dynamic Island: "
                "click-through error:",
                repr(error),
            )

        return False

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

        height = min(
            self.visual_height,
            WINDOW_HEIGHT,
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
            0.01,
            0.01,
            0.015,
            0.985,
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
                                    CORNER_RADIUS,
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

    def expand(self):

        self.target_width = float(
            EXPANDED_WIDTH
        )

        self.target_height = float(
            EXPANDED_HEIGHT
        )

        self.start_animation()

    def collapse(self):

        self.target_width = float(
            NORMAL_WIDTH
        )

        self.target_height = float(
            NORMAL_HEIGHT
        )

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

        self.charging_active = False

        self.collapse()

        self.queue_draw()

        return False

    # ========================================================
    # GENERIC EVENT
    # ========================================================

    def show_generic(self, data):

        self.generic_event = data

        self.generic_active = True

        self.expand()

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
