"""Translations with gettext. Catalogues live in `compartir_selector/locale/<lang>/LC_MESSAGES/` (bundled) and
in the system locale dir when installed as a package. The session's LANG/LANGUAGE decides; English is the source."""

import gettext
from pathlib import Path

DOMAIN = "compartir-selector"
LOCALE_DIRS = (Path(__file__).parent / "locale", Path("/usr/share/locale"))


def _load() -> gettext.NullTranslations:
    for directory in LOCALE_DIRS:
        try:
            return gettext.translation(DOMAIN, localedir=str(directory))
        except OSError:
            continue
    return gettext.NullTranslations()


_translations = _load()


def _(message: str) -> str:
    return _translations.gettext(message)
