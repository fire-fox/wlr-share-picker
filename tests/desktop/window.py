"""A test window for the headless desktop of tests/desktop/session.sh: nothing but a title and a label."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

app = Gtk.Application(application_id="dev.test.Window")


def on_activate(application):
    window = Gtk.ApplicationWindow(application=application, title="Test document")
    window.set_child(Gtk.Label(label="A test window"))
    window.present()


app.connect("activate", on_activate)
app.run([])
