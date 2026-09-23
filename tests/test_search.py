from wlr_share_picker import search


def test_normalize_strips_accents_and_case():
    assert search.normalize("Título CON Ñ") == "titulo con n"  # ñ folds to n too: typing "manana" finds "mañana"


def test_every_word_must_match_somewhere():
    assert search.matches("chrom roam", "Roamgate", "chromium")
    assert not search.matches("chrom teams", "Roamgate", "chromium")
    assert search.matches("", "anything")
    assert search.matches("pantalla", "Pantalla DP-1")
    assert search.matches("ventana", "Roamgate", "", "window") is False
