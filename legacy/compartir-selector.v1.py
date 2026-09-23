#!/usr/bin/env python3
"""Selector con miniaturas para compartir pantalla en mango (xdg-desktop-portal-wlr, chooser_type=dmenu).

El portal manda por stdin una línea por fuente, «Monitor: nombre descripción» o «Window: título (id)», y espera de
vuelta la línea elegida tal cual; salir sin imprimir nada es «cancelar». Este programa captura una miniatura de cada
fuente con grim (por salida, o por id de ventana con `-T`), las muestra en una cuadrícula y devuelve la línea.

Si algo falla antes de mostrar la ventana, cae a fuzzel para no dejar a Teams sin selector.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading

# gtk4-layer-shell tiene que cargarse antes que libwayland: desde Python solo se logra precargándolo. Si no,
# GTK abre una ventana normal (en mosaico) en vez de una capa encima de todo. Se relanza una vez con LD_PRELOAD.
_LS = "/usr/lib/libgtk4-layer-shell.so"
if os.path.exists(_LS) and _LS not in os.environ.get("LD_PRELOAD", ""):
    os.environ["LD_PRELOAD"] = (_LS + ":" + os.environ["LD_PRELOAD"]) if os.environ.get("LD_PRELOAD") else _LS
    os.execv(sys.executable, [sys.executable, *sys.argv])

FUZZEL = ["fuzzel", "--dmenu", "--prompt", "Compartir: ", "--lines", "12", "--width", "70"]
ANCHO_MINI = 320
FILAS = 3


def respaldo(lineas):
    r = subprocess.run(FUZZEL, input="".join(lineas), capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.exit(0)


lineas = sys.stdin.readlines()
if not lineas:
    sys.exit(0)

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gdk, GLib, Gtk
    from gi.repository import Gtk4LayerShell as Layer
except Exception:
    respaldo(lineas)

# --- fuentes -------------------------------------------------------------------------------------------------


def clientes_mango():
    """id de toplevel → (appid, título) según mango, para poner ícono y nombre de app."""
    try:
        d = json.loads(subprocess.run(["mmsg", "get", "all-clients"], capture_output=True, text=True, timeout=2).stdout)
        cs = d.get("clients", d if isinstance(d, list) else [])
        return {c["foreign_toplevel_id"]: c for c in cs if c.get("foreign_toplevel_id")}
    except Exception:
        return {}


CLIENTES = clientes_mango()
fuentes = []  # dicts: linea, tipo, nombre, detalle, grim(args), appid
for l in lineas:
    t = l.rstrip("\n")
    m = re.match(r"Monitor: (\S+)\s*(.*)", t)
    if m:
        fuentes.append(
            {"linea": l, "tipo": "monitor", "nombre": m.group(1), "detalle": m.group(2), "grim": ["-o", m.group(1)], "appid": ""}
        )
        continue
    m = re.match(r"Window: (.*) \(([0-9a-f]+)\)$", t)
    if m:
        c = CLIENTES.get(m.group(2), {})
        fuentes.append(
            {
                "linea": l,
                "tipo": "ventana",
                "nombre": m.group(1),
                "detalle": c.get("appid", ""),
                "grim": ["-T", m.group(2)],
                "appid": c.get("appid", ""),
            }
        )

if not fuentes:
    respaldo(lineas)

TMP = tempfile.mkdtemp(prefix="compartir-")


def miniatura(i, f):
    """Captura con grim. Límite corto: una ventana que ya se está compartiendo por el portal deja a grim colgado
    (comprobado con Chromium), y no debe frenar al resto; esa tarjeta queda sin imagen."""
    ruta = os.path.join(TMP, f"{i}.jpg")
    escala = "0.2" if f["tipo"] == "monitor" else "0.35"
    try:
        r = subprocess.run(["grim", "-s", escala, "-t", "jpeg", "-q", "70", *f["grim"], ruta], capture_output=True, timeout=2.5)
    except subprocess.TimeoutExpired:
        return None
    return ruta if r.returncode == 0 and os.path.exists(ruta) else None


# --- ventana -------------------------------------------------------------------------------------------------

CSS = b"""
window { background: rgba(19,19,19,0.95); color: #e2e2e2; font-family: system-ui; font-size: 15px; }
.titulo { font-size: 19px; font-weight: 700; color: #ffb866; margin: 6px 0 2px 0; }
.ayuda { color: #9a9a9a; font-size: 13px; margin-bottom: 8px; }
.tarjeta { background: #1f1f1f; border: 2px solid #2c2c2c; border-radius: 12px; padding: 8px; }
.tarjeta:hover { border-color: #6b5230; }
.tarjeta.activa { border-color: #ffb866; background: #2a2218; }
.tarjeta label.nombre { font-weight: 600; }
.tarjeta label.detalle { color: #9a9a9a; font-size: 12px; }
.sin { background: #0c0c0c; color: #555; border-radius: 6px; }
button.cancelar { background: #2a2a2a; color: #e2e2e2; border: 1px solid #444; border-radius: 8px; padding: 6px 14px; }
"""

ICONOS = {
    "chromium": "chromium",
    "firefox": "firefox",
    "teams-trabajo": "teams-for-linux",
    "teams-personal": "teams-for-linux",
    "org.kde.dolphin": "system-file-manager",
    "kitty": "kitty",
    "herdr": "utilities-terminal",
    "zapzap": "zapzap",
    "com.anthropic.Claude": "claude-desktop",
    "kopuz": "moe.kopuz.kopuz",
}


def icono_de(appid):
    if not appid:
        return "video-display"
    if appid.startswith("chrome-"):
        return "chromium"
    return ICONOS.get(appid, appid)


class Selector(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.erik.compartir")
        self.activa = 0
        self.tarjetas = []
        self.elegida = None

    def do_activate(self):
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        w = Gtk.ApplicationWindow(application=self, title="Compartir")
        Layer.init_for_window(w)
        Layer.set_layer(w, Layer.Layer.OVERLAY)
        Layer.set_keyboard_mode(w, Layer.KeyboardMode.EXCLUSIVE)
        Layer.set_namespace(w, "compartir-selector")
        w.set_default_size(4 * (ANCHO_MINI + 40) + 44, -1)
        caja = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, margin_top=18, margin_bottom=14, margin_start=22, margin_end=22, spacing=6
        )
        w.set_child(caja)
        t = Gtk.Label(label="¿Qué querés compartir?", xalign=0)
        t.add_css_class("titulo")
        caja.append(t)
        a = Gtk.Label(label="Flechas para moverte · Enter o clic para compartir · Esc para cancelar", xalign=0)
        a.add_css_class("ayuda")
        caja.append(a)
        self.grid = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            max_children_per_line=4,
            min_children_per_line=1,
            column_spacing=10,
            row_spacing=10,
            homogeneous=True,
            valign=Gtk.Align.START,
        )
        caja.append(self.grid)
        for i, f in enumerate(fuentes):
            self.grid.append(self.tarjeta(i, f))
        pie = Gtk.Box(halign=Gtk.Align.END, margin_top=8)
        b = Gtk.Button(label="Cancelar")
        b.add_css_class("cancelar")
        b.connect("clicked", lambda *_: self.terminar(None))
        pie.append(b)
        caja.append(pie)
        teclas = Gtk.EventControllerKey()
        teclas.connect("key-pressed", self.tecla)
        w.add_controller(teclas)
        self.marcar(0)
        w.present()
        threading.Thread(target=self.cargar_miniaturas, daemon=True).start()

    def tarjeta(self, i, f):
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.START)
        caja.add_css_class("tarjeta")
        img = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True)
        img.set_size_request(ANCHO_MINI, int(ANCHO_MINI * 5 / 8))
        img.add_css_class("sin")
        caja.append(img)
        fila = Gtk.Box(spacing=8)
        ic = Gtk.Image.new_from_icon_name("video-display" if f["tipo"] == "monitor" else icono_de(f["appid"]))
        ic.set_pixel_size(22)
        fila.append(ic)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        n = Gtk.Label(
            label=f["nombre"] if f["tipo"] == "ventana" else f"Pantalla {f['nombre']}", xalign=0, ellipsize=3, max_width_chars=34
        )
        n.add_css_class("nombre")
        col.append(n)
        d = Gtk.Label(
            label=f["detalle"] or ("Monitor completo" if f["tipo"] == "monitor" else "Ventana"),
            xalign=0,
            ellipsize=3,
            max_width_chars=34,
        )
        d.add_css_class("detalle")
        col.append(d)
        fila.append(col)
        caja.append(fila)
        clic = Gtk.GestureClick()
        clic.connect("released", lambda *_: self.terminar(i))
        caja.add_controller(clic)
        mov = Gtk.EventControllerMotion()
        mov.connect("enter", lambda *_: self.marcar(i))
        caja.add_controller(mov)
        self.tarjetas.append((caja, img))
        return caja

    def cargar_miniaturas(self):
        def una(i, f):
            ruta = miniatura(i, f)
            if ruta:
                GLib.idle_add(self.poner, i, ruta)
            else:
                GLib.idle_add(self.sin_imagen, i)

        for i, f in enumerate(fuentes):
            threading.Thread(target=una, args=(i, f), daemon=True).start()

    def sin_imagen(self, i):
        img = self.tarjetas[i][1]
        img.set_paintable(
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).lookup_icon(
                "image-missing", None, 48, 1, Gtk.TextDirection.NONE, 0
            )
        )
        return False

    def poner(self, i, ruta):
        img = self.tarjetas[i][1]
        img.remove_css_class("sin")
        img.set_filename(ruta)
        return False

    def marcar(self, i):
        self.tarjetas[self.activa][0].remove_css_class("activa")
        self.activa = i
        self.tarjetas[i][0].add_css_class("activa")

    def tecla(self, ctl, keyval, keycode, state):
        n = len(fuentes)
        por_fila = min(4, n) or 1
        k = Gdk.keyval_name(keyval)
        if k == "Escape":
            self.terminar(None)
        elif k in ("Return", "KP_Enter", "space"):
            self.terminar(self.activa)
        elif k in ("Right", "l"):
            self.marcar((self.activa + 1) % n)
        elif k in ("Left", "h"):
            self.marcar((self.activa - 1) % n)
        elif k in ("Down", "j"):
            self.marcar((self.activa + por_fila) % n)
        elif k in ("Up", "k"):
            self.marcar((self.activa - por_fila) % n)
        elif k and k.isdigit() and 0 < int(k) <= n:
            self.terminar(int(k) - 1)
        else:
            return False
        return True

    def terminar(self, i):
        self.elegida = fuentes[i]["linea"] if i is not None else None
        self.quit()


app = Selector()
app.run([])
for f in os.listdir(TMP):
    os.unlink(os.path.join(TMP, f))
os.rmdir(TMP)
if app.elegida:
    sys.stdout.write(app.elegida)
