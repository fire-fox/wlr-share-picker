# Changelog

## 0.4.1 — 2026-09-22
First public release.
- Releases from tags: GitHub workflow with wheel, sdist and a PKGBUILD with checksum; `scripts/release.sh`.
- README: features and every input (stdin, options, environment, config keys), with a test that keeps them listed.
- Where the pointer rests when the picker opens no longer overrides the preselection.
- The README screenshot is drawn from invented windows (`scripts/demo-screenshot.py`), never a real screen.
- Security: state files only in private directories owned by the user (0700, no symlinks, files 0600 written
  atomically); without `XDG_RUNTIME_DIR` the short-lived memory is off instead of falling back to `/tmp`.
- Security: upper bounds on every numeric setting; property-based tests (Hypothesis) of every input; invariant tests
  (no shell, no markup, no network); `SECURITY.md`.
- CI: the whole pipeline in `scripts/ci.sh`, run in a fresh Arch by `scripts/ci-container.sh` the same on GitHub and
  locally; Harden-Runner on every job; gitleaks and trufflehog on the history; zizmor, actionlint and poutine on the
  workflows; shellcheck; ruff with the bandit rules; dependency-review on pull requests; CodeQL, OpenSSF Scorecard
  and weekly mutation testing (mutmut); actions pinned by hash with Dependabot (7-day cooldown); tools outside Arch
  verified with Sigstore before running (`scripts/ci-tools.sh`).
- Desktop test in CI and before every release: a headless sway desktop with PipeWire and the real portal; the
  picker is driven with virtual key presses and the portal must hand out the chosen monitor or window.
- Tests reject invisible and direction-changing Unicode characters ("Trojan Source") and unexpected binary files.
- `CONTRIBUTING.md`: changes arrive as patches attached to an issue; pull requests are for collaborators.
- Fixed: a corrupt short-lived memory (`"requester_pid": Infinity`) crashed the picker; found by the property tests.
- Releases: built without write permissions, then signed and published by a separate job after the owner's
  approval; SPDX SBOMs of the package (signed) and of the build environment with grype's report; `SHA256SUMS`;
  signed build provenance for every file.
- A config value of the wrong type is reported and replaced by its default instead of crashing the picker.
- `config.example.toml` lists the tables last, so uncommenting `theme` or `debug` no longer lands them in `[auto]`/`[colors]`.
- The short-lived memory is never reused for a request whose app cannot be told, unless the choice was made just as blind.
- Keyboard moves scroll the grid to the active card; Up/Down stop at the edges; keypad digits and Enter work.
- Hover only follows real pointer movement, so scrolling under a still pointer no longer steals the selection.
- Window titles refresh live on the cards (and in the filter) together with the thumbnails.
- Thumbnails are decoded on the capture threads and refreshes only capture the cards the filter leaves visible.
- Typing what a card shows finds it, also translated text such as «Pantalla» on a monitor card.
- `[auto]` rules apply only when the requesting app is unambiguous.
- The dmenu fallback applies `hide_app_ids`/`hide_titles` as well.
- Window ids are treated as opaque: any id the portal sends is accepted and handed back verbatim to grim and the portal.
- After the relaunch, child processes (grim, compositor IPC, dmenu) get the original `LD_PRELOAD` instead of GTK's.
- With no dmenu installed the fallback exits 1 and says so, instead of logging a cancel by the user.
- CI runs in an Arch container (Ubuntu 24.04 has no gtk4-layer-shell); the suite no longer needs a session bus;
  build requires setuptools ≥ 77 (SPDX license) and no longer warns about the locale tree.

## 0.4.0 — 2026-09-22
- The title says which app is asking, found through the portal's D-Bus session, its PID and its systemd app scope.
- `[auto]` rules answer chosen apps without a dialog (`rustdesk = "DP-1"`), for remote sessions with nobody at the desk.

## 0.3.0 — 2026-09-22
- Type to filter the grid by title or app (accent-insensitive); Esc clears the filter first.
- The source shared last time is preselected (by window id, else by app); `remember_choice`.
- Live thumbnails: re-captured every `refresh_seconds` while the picker is open.
- App names from the real `.desktop` (`Name=`) instead of raw app ids.
- `hide_app_ids` / `hide_titles` to keep noise out of the grid.
- Theme: follows your GTK 4 palette (`~/.config/gtk-4.0/gtk.css`) or the desktop colour scheme; `theme` and `[colors]` overrides.
- Translations with gettext; Spanish included.
- CI on GitHub Actions (ruff, pytest, wheel). Hidden `--screenshot PNG` for documentation.

## 0.2.0 — 2026-09-22
- Rewritten as a package: protocol, compositor backends (mango, sway), captures, config, GTK and dmenu frontends.
- Second portal request within `reuse_choice_seconds` is answered with the same source (Chromium asks twice).
- Hard timeout per capture that kills the whole process group; temp files removed on exit and signals.
- Grid sized for the narrowest monitor, scroll, cards of uniform size for any window shape.
- Tests without a display, ruff, pyproject entry point, PKGBUILD.

## 0.1.0 — 2026-09-22
- Single-file picker: GTK 4 grid on a layer, one grim per source, fuzzel fallback.
