# Security

## What the picker protects
`wlr-share-picker` decides which monitor or window `xdg-desktop-portal-wlr` hands to an app that asked to share the
screen. Its job is that you, not the app, choose; so the answer it prints is always one of the sources the portal
offered (checked by property-based tests), and it only answers without a dialog in the two cases you enable:

- the same process asking again within `reuse_choice_seconds` (Chromium asks twice), and
- an `[auto]` rule for an unambiguously identified requester.

## What it does not protect against
- **Other programs of your own user.** On wlroots compositors any of them can capture the screen directly with
  `grim` or read your files; the portal dialog is about consent for well-behaved apps, not a sandbox.
- **Requesters that lie about who they are.** The requesting app is identified by its D-Bus connection, PID and
  systemd scope; a local process can pick its own name and scope. `[auto]` rules are a convenience, not a trust
  boundary, and they never fire when the requester is ambiguous.

## Design choices that matter
- Nothing runs through a shell: grim, the compositor IPC and the dmenu get argument lists; window titles go to the
  dmenu on stdin, never on its command line. GTK labels never parse markup, so a title cannot style the dialog.
- Small state files live only in `$XDG_RUNTIME_DIR/wlr-share-picker` and `$XDG_STATE_HOME/wlr-share-picker`,
  created 0700 and used only when they are real directories owned by you; files are written 0600, atomically and
  without following symlinks. Without `XDG_RUNTIME_DIR` the short-lived memory is off (there is no `/tmp` fallback).
- Thumbnails are temporary files in a private (0700) directory removed on exit, also on SIGTERM.
- No network access, no deserialisation of code (`pickle`, `eval`), no dependencies from PyPI.
- The config file is untrusted input too: wrong types and out-of-range values are replaced, never fatal.

## How it is checked
On every push and pull request (details in the README's *Continuous integration*): `gitleaks` and `trufflehog` over
the whole git history, `zizmor`, `actionlint` and `poutine` over the workflows, `shellcheck`, `ruff` with the bandit
security rules, and the test suite, which includes property-based tests (Hypothesis) of every input the picker
parses and tests of the invariants above (and that no invisible or direction-changing character, nor any binary
file outside a short list, is in the repository); an end-to-end test on a headless Wayland desktop through the
real portal;
`dependency-review` on pull requests. CodeQL, OpenSSF Scorecard and
mutation testing run weekly. Every job starts with Harden-Runner (egress audit, source tampering detection).

The pipeline is built to survive a compromised tool: actions are pinned by commit hash; tools Arch does not
package run only after their Sigstore signature is verified against their project's release workflow; the jobs
that run tools hold no secret and no write permission; the release is signed and published by a separate job that
runs only GitHub's own actions and waits for the owner's approval. Every release file carries a signed build
provenance attestation, the package a signed SBOM:

```bash
gh attestation verify wlr_share_picker-<version>-py3-none-any.whl --repo fire-fox/wlr-share-picker \
  --signer-workflow fire-fox/wlr-share-picker/.github/workflows/build.yml
sha256sum -c SHA256SUMS
```

## Reporting a vulnerability
Please report it privately through GitHub: **Security → Report a vulnerability** on this repository
(<https://github.com/fire-fox/wlr-share-picker/security/advisories/new>). Do not open a public issue. You can
expect an answer within a week. Only the latest release receives fixes.
