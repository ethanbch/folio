"""Rule-based query parsing: dates and file types, in French and English.

"le pdf du devis de la semaine dernière" → text "devis", type pdf, date range.
The matched words are removed from the text sent to the search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .kinds import KINDS
from .textnorm import fold, nfc

MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
    "janv": 1,
    "fevr": 2,
    "fev": 2,
    "avr": 4,
    "juil": 7,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_NAMES_FR = [
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]

NUMBERS = {
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "quinze": 15,
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "few": 3,
    "quelques": 3,
}

# Words that name a type of file → extensions.
TYPE_WORDS: dict[str, set[str]] = {
    "pdf": {"pdf"},
    "pdfs": {"pdf"},
    "excel": KINDS["spreadsheet"],
    "tableur": KINDS["spreadsheet"],
    "spreadsheet": KINDS["spreadsheet"],
    "feuille de calcul": KINDS["spreadsheet"],
    "xlsx": {"xlsx", "xlsm", "xls"},
    "xls": {"xls", "xlsx"},
    "csv": {"csv", "tsv"},
    "word": KINDS["document"],
    "docx": {"docx", "doc"},
    "doc word": KINDS["document"],
    "presentation": KINDS["presentation"],
    "presentations": KINDS["presentation"],
    "powerpoint": KINDS["presentation"],
    "ppt": KINDS["presentation"],
    "pptx": KINDS["presentation"],
    "keynote": KINDS["presentation"],
    "slides": KINDS["presentation"],
    "diapo": KINDS["presentation"],
    "diapos": KINDS["presentation"],
    "diaporama": KINDS["presentation"],
    "image": KINDS["image"],
    "images": KINDS["image"],
    "photo": KINDS["image"],
    "photos": KINDS["image"],
    "capture d'ecran": KINDS["image"],
    "capture ecran": KINDS["image"],
    "screenshot": KINDS["image"],
    "png": {"png"},
    "jpg": {"jpg", "jpeg"},
    "jpeg": {"jpg", "jpeg"},
    "heic": {"heic"},
    "video": KINDS["video"],
    "videos": KINDS["video"],
    "mp4": {"mp4"},
    "mov": {"mov"},
    "audio": KINDS["audio"],
    "musique": KINDS["audio"],
    "mp3": {"mp3"},
    "enregistrement audio": KINDS["audio"],
    "vocal": KINDS["audio"],
    "mail": KINDS["email"],
    "email": KINDS["email"],
    "e-mail": KINDS["email"],
    "courriel": KINDS["email"],
    "zip": KINDS["archive"],
    "archive zip": KINDS["archive"],
    "script": {"py", "sh", "js", "ts", "r", "m", "jl"},
    "python": {"py", "ipynb"},
    "notebook": {"ipynb"},
    "markdown": {"md", "markdown"},
    "txt": {"txt"},
    "epub": {"epub"},
    "ebook": KINDS["ebook"],
}
# Type words that are also ordinary words ("présentation du projet", "photos de vacances"):
# they set the type, and stay in the searched text.
KEEP_IN_TEXT = {
    "presentation",
    "presentations",
    "slides",
    "diapo",
    "diapos",
    "diaporama",
    "image",
    "images",
    "photo",
    "photos",
    "video",
    "videos",
    "audio",
    "musique",
    "vocal",
    "mail",
    "email",
    "e-mail",
    "courriel",
    "script",
    "notebook",
    "screenshot",
    "capture d'ecran",
    "capture ecran",
    "enregistrement audio",
    "ebook",
}

TYPE_LABELS = {
    frozenset(KINDS["spreadsheet"]): "Tableur",
    frozenset(KINDS["document"]): "Document Word",
    frozenset(KINDS["presentation"]): "Présentation",
    frozenset(KINDS["image"]): "Image",
    frozenset(KINDS["video"]): "Vidéo",
    frozenset(KINDS["audio"]): "Audio",
    frozenset(KINDS["email"]): "E-mail",
    frozenset(KINDS["archive"]): "Archive",
}

_FILLER = re.compile(
    r"^(?:(?:le|la|les|un|une|des|du|de|d'|l'|mon|ma|mes|en|au|the|my|a|an|in|from|of|dans|sur|pour)\s+)+|(?:\s+(?:le|la|les|un|une|des|du|de|d'|l'|mon|ma|mes|en|au|the|my|a|an|in|from|of|dans|sur|pour))+$",
    re.IGNORECASE,
)


@dataclass
class Parsed:
    text: str  # what is left to search
    exts: set[str] = field(default_factory=set)
    type_label: str | None = None
    date_from: float | None = None  # epoch seconds
    date_to: float | None = None
    date_label: str | None = None
    year_hint: int | None = None  # a bare year: boost, not filter
    name_terms: str = ""  # extra words for names: "mai 2022" → "2022 05"
    recent: bool = False  # "récent", "dernier"
    chips: list[dict] = field(default_factory=list)


def _ts(d: date) -> float:
    return datetime(d.year, d.month, d.day).timestamp()


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return start, end


def _num(s: str) -> int:
    return int(s) if s.isdigit() else NUMBERS.get(s, 1)


def parse(query: str, today: date | None = None, disabled: set[str] | None = None) -> Parsed:
    """disabled: chip ids the user removed ("type", "date")."""
    today = today or date.today()
    disabled = disabled or set()
    # Match on folded text; cut the same characters from the original, so accents survive.
    orig = " " + nfc(query.strip()) + " "
    folded, owner = [], []
    for i, ch in enumerate(orig):
        f = fold(ch)
        folded.append(f)
        owner.extend([i] * len(f))
    q = "".join(folded)
    removed = [False] * len(orig)
    p = Parsed(text="")
    found_date: tuple[date, date, str] | None = None

    def take(pattern: str) -> re.Match | None:
        nonlocal q
        m = re.search(pattern, q)
        if m:
            q = q[: m.start()] + " " * (m.end() - m.start()) + q[m.end() :]
            for j in range(m.start(), m.end()):
                removed[owner[j]] = True
        return m

    N = r"(\d+|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|quinze|quelques|a|an|one|two|three|few)"
    monday = today - timedelta(days=today.weekday())
    rules: list[tuple[str, callable]] = [
        (r"\b(?:avant[- ]hier|day before yesterday)\b", lambda m: (today - timedelta(2), today - timedelta(1), "Avant-hier")),
        (r"\b(?:hier|yesterday)\b", lambda m: (today - timedelta(1), today, "Hier")),
        (r"\b(?:aujourd'?hui|aujourd hui|today|ce matin|this morning)\b", lambda m: (today, today + timedelta(1), "Aujourd'hui")),
        (r"\b(?:cette semaine|this week)\b", lambda m: (monday, today + timedelta(1), "Cette semaine")),
        (
            r"\b(?:la |l')?(?:semaine (?:derniere|passee)|derniere semaine|last week|past week)\b",
            lambda m: (monday - timedelta(7), today + timedelta(1), "Semaine dernière"),
        ),
        (r"\b(?:ce mois[- ]ci|ce mois|this month)\b", lambda m: (today.replace(day=1), today + timedelta(1), "Ce mois-ci")),
        (
            r"\b(?:le )?(?:mois (?:dernier|passe)|dernier mois|last month|past month)\b",
            lambda m: (
                (_month_range(today.year - (today.month == 1), (today.month - 2) % 12 + 1)[0]),
                today + timedelta(1),
                "Mois dernier",
            ),
        ),
        (r"\b(?:cette annee|this year)\b", lambda m: (date(today.year, 1, 1), today + timedelta(1), str(today.year))),
        (
            r"\b(?:l'?annee (?:derniere|passee)|annee derniere|last year)\b",
            lambda m: (date(today.year - 1, 1, 1), date(today.year, 1, 1), str(today.year - 1)),
        ),
        (rf"\b(?:il y a|ya|y a)\s+{N}\s+(jours?|j)\b|\b{N}\s+(days?)\s+ago\b", lambda m: _ago(today, m, "day")),
        (rf"\b(?:il y a|ya|y a)\s+{N}\s+(semaines?)\b|\b{N}\s+(weeks?)\s+ago\b", lambda m: _ago(today, m, "week")),
        (rf"\b(?:il y a|ya|y a)\s+{N}\s+(mois)\b|\b{N}\s+(months?)\s+ago\b", lambda m: _ago(today, m, "month")),
        (rf"\b(?:il y a|ya|y a)\s+{N}\s+(ans?|annees?)\b|\b{N}\s+(years?)\s+ago\b", lambda m: _ago(today, m, "year")),
    ]
    for pattern, fn in rules:
        if found_date:
            break
        m = take(pattern)
        if m:
            found_date = fn(m)

    if not found_date:
        month_alt = "|".join(sorted(MONTHS, key=len, reverse=True))
        # "en mars", "du mois de mars", "mars 2024", "en mars 2024", "in march"
        m = take(rf"\b(?:(?:en|in|du mois de|mois de|de|d')\s+({month_alt})(?:\s+((?:19|20)\d\d))?|({month_alt})\s+((?:19|20)\d\d))\b")
        if m:
            name = m.group(1) or m.group(3)
            year = m.group(2) or m.group(4)
            month = MONTHS[name]
            y = int(year) if year else (today.year if month <= today.month else today.year - 1)
            start, end = _month_range(y, month)
            found_date = (start, end, f"{MONTH_NAMES_FR[month].capitalize()} {y}")
            if year:
                p.name_terms = f"{y} {month:02d}"
    if not found_date:
        m = take(r"\b(?:en|in|de|depuis)\s+((?:19|20)\d\d)\b")
        if m:
            y = int(m.group(1))
            found_date = (date(y, 1, 1), date(y + 1, 1, 1), str(y))
    if not found_date:
        m = re.search(r"\b((?:19|20)\d\d)\b", q)
        if m and 1990 <= int(m.group(1)) <= today.year + 1:
            p.year_hint = int(m.group(1))  # stays in the text: years often appear in names

    if take(r"\b(?:recents?|recemment|dernierement|recent|recently|latest|nouveaux?|nouvelles?)\b"):
        p.recent = True

    # Types: longest phrases first.
    for word in sorted(TYPE_WORDS, key=len, reverse=True):
        pattern = rf"(?<![\w-]){re.escape(word)}(?![\w-])"
        m = re.search(pattern, q) if word in KEEP_IN_TEXT else take(pattern)
        if m:
            p.exts |= TYPE_WORDS[word]
            label = TYPE_LABELS.get(frozenset(TYPE_WORDS[word]))
            if not label:
                label = " / ".join(sorted(TYPE_WORDS[word])).upper() if len(TYPE_WORDS[word]) <= 2 else word.capitalize()
            p.type_label = label if not p.type_label else p.type_label + ", " + label
    if p.exts:
        if "type" in disabled:
            p.exts = set()
        else:
            p.chips.append({"id": "type", "label": p.type_label})

    if found_date:
        start, end, label = found_date
        if "date" not in disabled:
            p.date_from, p.date_to, p.date_label = _ts(start), _ts(end), label
            p.chips.append({"id": "date", "label": label})

    text = "".join(" " if removed[i] else c for i, c in enumerate(orig))
    text = re.sub(r"\s+", " ", text).strip()
    p.text = _FILLER.sub("", text).strip()
    return p


def _ago(today: date, m: re.Match, unit: str) -> tuple[date, date, str]:
    groups = [g for g in m.groups() if g]
    n = _num(groups[0]) if groups else 1
    if unit == "day":
        center, slack = today - timedelta(n), max(1, n // 3)
        label = f"Il y a {n} jour{'s' * (n > 1)}"
    elif unit == "week":
        center, slack = today - timedelta(7 * n), 4 + 2 * n
        label = f"Il y a {n} semaine{'s' * (n > 1)}"
    elif unit == "month":
        center, slack = today - timedelta(30 * n), 20 + 5 * n
        label = f"Il y a {n} mois"
    else:
        center, slack = today - timedelta(365 * n), 200
        label = f"Il y a {n} an{'s' * (n > 1)}"
    return center - timedelta(slack), min(today + timedelta(1), center + timedelta(slack + 1)), label
