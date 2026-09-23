"""Type-to-filter matching: accent-insensitive, case-insensitive, every word of the query must appear somewhere."""

import unicodedata


def normalize(text: str) -> str:
    """Lowercase and strip diacritics: 'Título' → 'titulo'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def matches(query: str, *texts: str) -> bool:
    """True when every word of `query` is found in at least one of `texts`. An empty query matches everything."""
    words = normalize(query).split()
    if not words:
        return True
    haystack = " ".join(normalize(t) for t in texts if t)
    return all(word in haystack for word in words)
