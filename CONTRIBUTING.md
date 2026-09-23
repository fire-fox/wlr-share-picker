# Contributing

Thanks for your interest. wlr-share-picker decides which screen an app gets and has a single maintainer, so
changes come in through a deliberately careful path.

## Bugs and ideas

Open an issue with what you ran (compositor, `xdg-desktop-portal-wlr` version), what you expected and what
happened. The picker's log helps: set `WLR_SHARE_PICKER_DEBUG=1` for the portal and read
`journalctl --user -u xdg-desktop-portal-wlr`. **The log contains your window titles: remove anything private
before pasting it.**

Security problems never go in an issue: see [SECURITY.md](SECURITY.md).

## Sending a change

Pull requests are open to collaborators only. To send a change:

1. Open an issue first, describing the problem and how you would solve it, so we agree before you write code.
2. Make the change in your clone: one logical commit per change, with tests, and every check passing (below).
3. Turn your commits into patches with `git format-patch origin/main` and attach the `.patch` files to the issue.
4. The maintainer reads them and applies them with `git am`, so the commits keep your name.

For larger or recurring work, ask in the issue: a pull request can be opened for it, or you can become a
collaborator.

## What every change must pass

- The same checks as CI: `scripts/ci-container.sh checks` and `scripts/ci-container.sh desktop` (podman or
  docker; see the README's *Development* and *Continuous integration*).
- Code, comments, interface texts and logs in English; `ruff` formatting; tests for new behaviour.
- No new dependency from PyPI.
- No binary files and no invisible or direction-changing Unicode characters (the tests reject both).
- Changes to `.github/`, `scripts/`, `tests/desktop/` or `packaging/` run in CI and in the release: explain them
  in the issue. They are reviewed line by line and may be rewritten by the maintainer.
- If an AI assistant wrote part of the change, say so, and make sure you understand and have run every line.

## License

By sending a change you agree that it is released under this project's [MIT license](LICENSE).
