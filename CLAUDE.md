# compartir-selector — selector con miniaturas para compartir pantalla

## Qué es
Selector de fuentes para `xdg-desktop-portal-wlr`: cuando Teams, Chromium u OBS piden compartir pantalla, el portal
lanza este programa con la lista de monitores y ventanas, y este muestra una cuadrícula con miniatura, ícono y título
de cada una. Sirve en cualquier compositor que use el portal wlr (mango, sway, river, niri…). Nació el 2026-09-22
porque el portal wlr no trae selector y los que existen con miniaturas son solo para el portal de Hyprland.
Personal, en piloto: en uso diario en la PC de Erik.

## Stack
Paquete Python (`compartir_selector/`) sin dependencias de PyPI: GTK 4, gtk4-layer-shell y `grim` del sistema.
`pyproject.toml` (PEP 621, entry point), `tests/` con pytest, `ruff` para lint y formato, `packaging/PKGBUILD`,
CI de GitHub en contenedor `archlinux` (Ubuntu 24.04 no empaqueta gtk4-layer-shell).
**Todo el código va en inglés** (identificadores, textos de la interfaz, logs y comentarios): está pensado para
publicarse. Este CLAUDE.md y los mensajes con Erik siguen en español.

## Estructura
| Módulo | Responsabilidad |
|---|---|
| `cli.py` | `main()`: stdin → relanzo con LD_PRELOAD → frontend → stdout. Códigos de salida 0/1/2. |
| `protocol.py` | Contrato dmenu del portal: `Source`, `parse()`. Puro, sin GTK ni subprocesos. |
| `compositor.py` | app id/título por id de toplevel: backends `Mango` (`mmsg`), `Sway` (`swaymsg`), `NoCompositor`. Añadir uno = clase + `BACKENDS`. |
| `icons.py` | Ícono y nombre (`Name=`) desde el `.desktop` real del app id (`candidates()` es puro) → alias → genérico. |
| `captures.py` | `Capturer`: grim por fuente, pool acotado, timeout que mata el grupo de procesos, temporales con limpieza. |
| `config.py` | `Config` (defaults) + `config.toml` + env. Nunca lanza: valida y avisa. |
| `ui_gtk.py` | Solo presentación: capa overlay, columnas según el monitor más estrecho, scroll que sigue a la tarjeta activa, `Thumbnail` de caja fija, filtro (`SearchEntry` con foco + teclas en fase CAPTURE), refresco periódico de miniaturas y títulos, `--screenshot` oculto para docs. |
| `ui_dmenu.py` | Respaldo fuzzel/wofi/bemenu/rofi; rechaza líneas que el portal no mandó. |
| `paths.py` | Directorios privados (`$XDG_RUNTIME_DIR`/`$XDG_STATE_HOME` + `compartir-selector`, 0700, dueño propio, sin symlinks) y escritura atómica 0600. Sin `XDG_RUNTIME_DIR` no hay memoria corta (nunca `/tmp`). |
| `recent.py` | Memoria corta en `$XDG_RUNTIME_DIR` (`reuse_choice_seconds`: segunda llamada seguida → misma fuente sin diálogo) y persistente en `$XDG_STATE_HOME` (`remember_choice`: preselección). |
| `requester.py` | Quién pide: sesión del portal (`/org/freedesktop/portal/desktop/session/<sender>/<token>`) → `GetConnectionUnixProcessID` → cgroup `app-<id>-<pid>.scope`. Sesiones ya vistas en `$XDG_RUNTIME_DIR/…/sessions-seen.json`. Reglas `[auto]`. |
| `search.py` | Filtro por tecleo: sin acentos ni mayúsculas, todas las palabras deben aparecer. Puro. |
| `theme.py` | Paleta: `@define-color` de `~/.config/gtk-4.0/gtk.css` (DMS/matugen) → preset dark/light por color-scheme → `[colors]` del toml. Genera el CSS. |
| `i18n.py` | gettext; catálogos en `locale/<lang>/LC_MESSAGES/` (`scripts/update-locales.sh` compila los .mo, que van commiteados). |
| `logs.py` | Logging a stderr (cae en el journal del portal). |
`legacy/compartir-selector.v1.py` es la versión de un solo archivo, archivada como referencia.
`compartir-selector` en la raíz es el lanzador para usar desde el repo (`~/.local/bin` apunta ahí).

## Cómo correr
```bash
printf 'Monitor: DP-1 ASUS\nWindow: Título (idhex)\n' | ./compartir-selector --debug   # ids de `mmsg get all-clients`
./scripts/demo-screenshot.py                                                         # regenera docs/screenshot.png con ventanas inventadas
./compartir-selector --screenshot /tmp/x.png < fuentes.txt                           # captura con ventanas REALES: solo para mirar, nunca al repo
scripts/release.sh X.Y.Z && git push && git push origin vX.Y.Z                      # release: el workflow publica wheel, sdist y PKGBUILD
./scripts/update-locales.sh                                                          # tras tocar un .po
./scripts/smoke-keys.sh fuentes.txt                                                  # teclas reales vía wtype contra la ventana
ruff check . && ruff format --check . && python3 -m pytest -q                        # todo sin display (incluye Hypothesis)
GH_TOKEN=$(gh auth token) scripts/ci-container.sh checks                            # el CI entero, igual que en GitHub (Arch limpio, ~5 min)
scripts/ci-container.sh mutation /tmp/mut                                            # mutation testing (mutmut), informe en /tmp/mut/mutation.md
grep chooser_cmd ~/.config/xdg-desktop-portal-wlr/config                             # debe apuntar a ~/.local/bin/compartir-selector
systemctl --user restart xdg-desktop-portal-wlr.service                              # el portal lee su config solo al arrancar
```
Config del portal en `dotfiles/config/xdg-desktop-portal-wlr/config`. Config propia opcional: `config.example.toml`.

## Repo público
`fire-fox/compartir-selector` es público (excepción a la regla de repos privados). Nada del escritorio real entra
al repo: la imagen del README sale solo de `scripts/demo-screenshot.py`, `.gitignore` bloquea otras imágenes y las
listas de fuentes, y el CI corre gitleaks sobre todo el historial. Los commits van con el correo noreply de GitHub
(`git config user.email` local del repo). La sección «What has been tested» del README se actualiza con cada cosa
que se pruebe de verdad; no se afirma nada que no se haya corrido.
Seguridad (detalle en `SECURITY.md` y en «Continuous integration» del README): todo el CI vive en `scripts/ci.sh`
y corre en un Arch limpio (`scripts/ci-container.sh`), igual en GitHub y en local. Los jobs corren en la VM (no
`container:`) porque Harden-Runner no soporta jobs en contenedor. trufflehog, grype y poutine no están en Arch:
`scripts/ci-tools.sh` baja la última release y la verifica con cosign contra el workflow de release de su repo
(identidades en el script). OpenGrep se descartó: su repo de reglas está archivado. El contenedor nunca recibe
tokens; la release se construye sin permisos de escritura y se firma/publica en otro job (`build.yml`, reusable)
que solo corre actions de GitHub y espera aprobación en el environment `release`. ruff con reglas `S` (excepciones
justificadas en su línea); zizmor sin hallazgos (el único `ignore` lleva su motivo). mutmut: ~2/3 de mutantes
cazados en el código que los tests recorren (flojos: `cli`, `captures`, `icons`, `i18n`); `ui_gtk` y `cli` casi no
los ve porque se prueban con escritorio real y subprocesos.

## Contrato con el portal
Modo `chooser_type=dmenu`: recibe por stdin una línea por fuente, «Monitor: nombre descripción» o «Window: título (id)»,
y debe imprimir la línea elegida tal cual. Salir sin imprimir nada es cancelar. El id es el de
`ext-foreign-toplevel-list-v1`, el mismo que `grim -T` acepta y que mango expone como `foreign_toplevel_id`. Es opaco
(hex en wlroots): `Source.id` va en minúsculas solo como clave de búsqueda; a grim y al portal va `raw_id`, tal cual llegó.

## Quirks
- gtk4-layer-shell tiene que cargarse antes que libwayland: desde Python solo se logra con `LD_PRELOAD`, así que
  `cli.relaunch_with_layer_shell()` reemplaza el proceso una vez (marca `COMPARTIR_SELECTOR_RELAUNCHED`). Sin eso la
  ventana sale en mosaico en vez de como capa encima de todo. Ya relanzado, `LD_PRELOAD` vuelve a su valor original
  (`COMPARTIR_SELECTOR_PRELOAD_BEFORE`): si no, cada grim/mmsg/dmenu hijo cargaba GTK entero (mmsg 4 → 16 ms).
- Una ventana que YA se está compartiendo deja a `grim -T` colgado (comprobado con Chromium). Cada captura tiene
  timeout y al vencer se mata su grupo de procesos entero; la tarjeta queda «sin imagen» y no frena a las demás.
- `Gtk.Picture` con la textura directa pide altura proporcional al ancho de la celda: una ventana vertical estira
  la fila. Por eso `Thumbnail` (paintable de caja fija) dibuja la textura centrada dentro.
- `Gio.DesktopAppInfo.new` lanza `TypeError` (no devuelve None) si el `.desktop` no existe; en PyGObject ≥ 3.56 vive
  en `GioUnix`. `icons._desktop()` cubre ambas cosas.
- En mango 0.17.3 `grim -T` fallaba con «Invalid stride» salvo anchos múltiplos de 4: lo arregla un parche propio de
  mango (memoria `mango-0-17-fuga-memoria`). Sin ese parche el selector funciona pero casi ninguna ventana trae miniatura.
- Teclado: el filtro (`SearchEntry`) tiene el foco y recibe las letras; el `EventControllerKey` de la ventana va en
  fase CAPTURE y atiende antes flechas, Enter, Esc y dígitos. Con `set_key_capture_widget` el entry se tragaba todo
  eso (bug encontrado con `scripts/smoke-keys.sh`). Con filtro activo los dígitos filtran, no eligen.
- Hover: un `enter` por tarjeta también salta cuando el scroll de teclado desliza tarjetas bajo el puntero quieto
  y roba la selección. Por eso un único `EventControllerMotion` en la ventana marca solo si cambian las
  coordenadas (`_on_pointer` + `Window.pick`). El scroll a la tarjeta activa usa `Gtk.Viewport.scroll_to` (GTK ≥ 4.12).
- `config.load` descarta con aviso cada valor cuyo tipo no coincide con el default del campo (bool ≠ int; float
  acepta int). En TOML toda clave tras `[tabla]` pertenece a ella: en `config.example.toml` las tablas van al final
  (lo cubre un test).
- El portal wlr compara la respuesta con el título ACTUAL de la ventana (`chooser.c`): si cambió mientras el diálogo
  estaba abierto, la rechaza y loguea «no output found». `protocol.refresh_title()` reconstruye la línea con el
  título que reporta el compositor justo antes de responder.
- «wlroots: no output found» en el journal del portal = el selector no imprimió nada (cancelación) o la línea no
  coincidió; el portal no distingue. Nuestros INFO «asked/answered/cancelled» lo aclaran.
- El refresco de miniaturas salta las fuentes cuyo grim se colgó (`Capturer.timed_out`) y no pisa una miniatura
  buena con un fallo posterior.
- El portal wlr no pasa `app_id` al chooser; `requester.py` lo deduce por D-Bus (3 ms). Apps lanzadas fuera de un scope
  systemd (terminal) quedan por nombre de proceso. Si ya hay una app compartiendo, la nueva sesión es la solicitante.
  La memoria corta solo se reutiliza si el PID solicitante coincide con el de la elección (0 = desconocido solo
  coincide con 0).
- Multimonitor: la capa la ubica el compositor (monitor activo) y GTK no dice cuál; las columnas se calculan con
  el monitor más estrecho para que la cuadrícula quepa en cualquiera.
- Chromium pide dos veces al portal (vista previa y luego compartir). Lo cubre `recent.py`: la segunda llamada dentro
  de `reuse_choice_seconds` responde sola con la misma fuente (por id, no por título). El mecanismo estándar
  (`restore_token`) existe en Chromium 153 y en xdpw 0.8, pero xdpw solo restaura monitores, nunca ventanas.
  La `Gtk.Application` es `NON_UNIQUE` por si dos selectores coinciden.

## Pendiente
- [ ] Chromium pide dos veces: el portal wlr solo restaura monitores (verificado por D-Bus el 2026-09-22); para ventanas
  lo cubre `reuse_choice_seconds`. Falta confirmar con Chromium real si el token llega en el caso monitor (`-l DEBUG`).
- [ ] El portal wlr cayó 4 veces el 2026-09-22 (11:30-11:33) al cerrar un stream de PipeWire (`pw_proxy_destroy`) y la
  instancia reiniciada quedó sin entregar el primer frame de las ventanas (vista previa vacía en Chromium hasta mover
  el mouse). Un `systemctl --user restart xdg-desktop-portal-wlr` lo curó. Si vuelve: valorar compilar el portal de
  master (commits de agosto sobre frames) como se hizo con mango.
- [ ] Crear el repo público en `fire-fox`, subir y publicar `v0.4.1` (todo preparado; espera el OK de Erik). ANTES del
  primer tag: crear el environment `release` con Erik como revisor obligatorio (si no, GitHub lo crea sin protección).
- [ ] Tras las primeras corridas en GitHub: pasar Harden-Runner de `egress-policy: audit` a `block` con los dominios
  que muestren sus informes (runners, pacman mirrors, github.com, sigstore, grype DB).
- [ ] Probar con más de un monitor y con escala fraccional/HiDPI (solo se usó un monitor a escala 1).
- [ ] Probar el backend `Sway` en un sway real (está escrito contra el JSON documentado, sin probar en vivo).
- [ ] PKGBUILD: apunta al tarball del tag en GitHub; probar `makepkg -si` con el de la primera release.
