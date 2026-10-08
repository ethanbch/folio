from datetime import date, datetime

from folio.queryparse import parse

TODAY = date(2026, 10, 8)  # a Thursday


def ts(y, m, d):
    return datetime(y, m, d).timestamp()


def test_type_and_relative_week():
    p = parse("le pdf du devis de la semaine dernière", today=TODAY)
    assert p.text == "devis"
    assert p.exts == {"pdf"}
    assert p.date_from == ts(2026, 9, 28)
    assert p.date_label == "Semaine dernière"


def test_month_without_year_is_the_last_past_one():
    p = parse("facture edf en mars", today=TODAY)
    assert p.text == "facture edf"
    assert p.date_from == ts(2026, 3, 1) and p.date_to == ts(2026, 4, 1)
    p = parse("relevé en décembre", today=TODAY)
    assert p.date_from == ts(2025, 12, 1)


def test_month_and_year():
    p = parse("notes de cours mars 2025", today=TODAY)
    assert p.text == "notes de cours"
    assert p.date_from == ts(2025, 3, 1)


def test_bare_year_stays_in_text():
    p = parse("bilan 2024", today=TODAY)
    assert p.text == "bilan 2024"
    assert p.year_hint == 2024
    assert p.date_from is None


def test_ago():
    p = parse("présentation stage il y a 2 mois", today=TODAY)
    # "présentation" is also an ordinary word: it sets the type and stays in the text.
    assert p.text == "présentation stage"
    assert p.exts >= {"pptx", "key"}
    assert p.date_from < ts(2026, 8, 8) < p.date_to


def test_accents_and_case_survive():
    p = parse("Relevé de compte hier", today=TODAY)
    assert p.text == "Relevé de compte"
    assert p.date_label == "Hier"


def test_disabled_chips():
    p = parse("excel budget hier", today=TODAY, disabled={"type"})
    assert not p.exts
    assert p.date_from is not None
    assert [c["id"] for c in p.chips] == ["date"]


def test_english():
    p = parse("slides from last week", today=TODAY)
    assert p.exts and p.date_from == ts(2026, 9, 28)


def test_format_words_leave_the_text():
    p = parse("excel budget vacances", today=TODAY)
    assert p.text == "budget vacances" and "xlsx" in p.exts


def test_month_year_adds_name_terms():
    p = parse("composition du stoxx 600 mai 2022", today=TODAY)
    assert p.name_terms == "2022 05"
    assert p.date_from == ts(2022, 5, 1)


def test_only_filters():
    p = parse("pdf", today=TODAY)
    assert p.text == "" and p.exts == {"pdf"}
