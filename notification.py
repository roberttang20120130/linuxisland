#!/usr/bin/env python3

import json
import urllib.request

from gi.repository import Gio, GLib


ISLAND_URL = "http://127.0.0.1:8765/event"

BORDER = "#9C27B0"

DBUS_NAME = "org.freedesktop.Notifications"
DBUS_PATH = "/org/freedesktop/Notifications"

INTROSPECTION_XML = """
<node>
  <interface name="org.freedesktop.Notifications">
    <method name="Notify">
      <arg type="s" name="app_name" direction="in"/>
      <arg type="u" name="replaces_id" direction="in"/>
      <arg type="s" name="app_icon" direction="in"/>
      <arg type="s" name="summary" direction="in"/>
      <arg type="s" name="body" direction="in"/>
      <arg type="as" name="actions" direction="in"/>
      <arg type="a{sv}" name="hints" direction="in"/>
      <arg type="i" name="expire_timeout" direction="in"/>
      <arg type="u" name="id" direction="out"/>
    </method>
    <method name="CloseNotification">
      <arg type="u" name="id" direction="in"/>
    </method>
    <method name="GetCapabilities">
      <arg type="as" name="capabilities" direction="out"/>
    </method>
    <method name="GetServerInformation">
      <arg type="s" name="name" direction="out"/>
      <arg type="s" name="vendor" direction="out"/>
      <arg type="s" name="version" direction="out"/>
      <arg type="s" name="spec_version" direction="out"/>
    </method>
    <signal name="NotificationClosed">
      <arg type="u" name="id"/>
      <arg type="u" name="reason"/>
    </signal>
    <signal name="ActionInvoked">
      <arg type="u" name="id"/>
      <arg type="s" name="action_key"/>
    </signal>
  </interface>
</node>
"""


def notify_island(value, title="", duration=3, border=BORDER):
    data = json.dumps({
        "type": "notify",
        "title": value,
        "value": "",
        "border": border,
        "border_width": 2,
        "border_radius": 16,
        "duration": duration,
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


class NotificationDaemon:
    def __init__(self):
        self.next_id = 1
        self.loop = None
        self.iface_info = Gio.DBusNodeInfo.new_for_xml(
            INTROSPECTION_XML
        ).interfaces[0]

    def handle_notify(self, connection, parameters, invocation):
        app_name = parameters[0]
        replaces_id = parameters[1]
        app_icon = parameters[2]
        summary = parameters[3]
        body = parameters[4]
        actions = parameters[5]
        hints = parameters[6]
        expire_timeout = parameters[7]

        if replaces_id:
            notification_id = replaces_id
        else:
            notification_id = self.next_id
            self.next_id += 1

        value = summary or body or app_name
        title = ""

        if expire_timeout is None or expire_timeout < 0:
            duration = 3
        elif expire_timeout == 0:
            duration = 10
        else:
            duration = max(1, expire_timeout // 1000)

        notify_island(value, title=title, duration=duration)

        print(f"[{notification_id}] {value}", flush=True)

        invocation.return_value(GLib.Variant("(u)", (notification_id,)))

        GLib.idle_add(self._emit_closed, connection, notification_id, 1)

    def _emit_closed(self, connection, notification_id, reason):
        connection.emit_signal(
            None,
            DBUS_PATH,
            DBUS_NAME,
            "NotificationClosed",
            GLib.Variant("(uu)", (notification_id, reason)),
        )
        return False

    def handle_close(self, connection, parameters, invocation):
        notification_id = parameters[0]
        connection.emit_signal(
            None,
            DBUS_PATH,
            DBUS_NAME,
            "NotificationClosed",
            GLib.Variant("(uu)", (notification_id, 3)),
        )
        invocation.return_value(None)

    def handle_get_capabilities(self, connection, parameters, invocation):
        invocation.return_value(
            GLib.Variant("(as)", (["body", "icon-static"],))
        )

    def handle_get_server_info(self, connection, parameters, invocation):
        invocation.return_value(
            GLib.Variant(
                "(ssss)",
                ("rebort-island", "local", "1.0", "1.2"),
            )
        )

    def on_method_call(
        self,
        connection,
        sender,
        object_path,
        interface_name,
        method_name,
        parameters,
        invocation,
    ):
        try:
            if method_name == "Notify":
                self.handle_notify(connection, parameters, invocation)
            elif method_name == "CloseNotification":
                self.handle_close(connection, parameters, invocation)
            elif method_name == "GetCapabilities":
                self.handle_get_capabilities(connection, parameters, invocation)
            elif method_name == "GetServerInformation":
                self.handle_get_server_info(connection, parameters, invocation)
            else:
                invocation.return_error_literal(
                    Gio.dbus_error_quark(),
                    Gio.DBusError.UNKNOWN_METHOD,
                    f"Unknown method: {method_name}",
                )
        except Exception as error:
            print("D-Bus handler error:", error, flush=True)
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.FAILED,
                str(error),
            )

    def on_bus_acquired(self, connection, name):
        connection.register_object(
            DBUS_PATH,
            self.iface_info,
            self.on_method_call,
            None,
            None,
        )
        print(f"notify_daemon: acquired {name}", flush=True)

    def on_name_lost(self, connection, name):
        print(f"notify_daemon: lost {name}", flush=True)
        if self.loop:
            self.loop.quit()

    def register(self):
        Gio.bus_own_name(
            Gio.BusType.SESSION,
            DBUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self.on_bus_acquired,
            None,
            self.on_name_lost,
        )

    def run(self):
        self.loop = GLib.MainLoop()
        self.register()
        print("notify_daemon: starting.", flush=True)
        self.loop.run()


def main():
    NotificationDaemon().run()


if __name__ == "__main__":
    main()
