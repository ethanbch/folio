"""Text normalisation shared by indexing and queries.

File names are split before they reach tantivy's analyzer (lowercase, ASCII
folding, French stemming): snake_case, camelCase, kebab-case, dots, and digits
glued to letters ("rapport2024" → "rapport 2024", "20240312" → "2024 03 12").
"""

from __future__ import annotations

import re
import unicodedata

_CAMEL = re.compile(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Þ])|(?<=[A-ZÀ-Þ])(?=[A-ZÀ-Þ][a-zà-ÿ])")
_LETTER_DIGIT = re.compile(r"(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])")
_SEPARATORS = re.compile(r"[_\-.+,;:()\[\]{}#@&=~'’\"`/\\|<>!?*]+")
_GLUED_DATE = re.compile(r"\b((?:19|20)\d\d)(0[1-9]|1[0-2])([0-3]\d)?\b")
_SPACES = re.compile(r"\s+")


def split_name(text: str) -> str:
    """Split an identifier-like name into words, keeping case and accents."""
    text = _SEPARATORS.sub(" ", text)
    text = _CAMEL.sub(" ", text)
    text = _LETTER_DIGIT.sub(" ", text)
    text = _GLUED_DATE.sub(lambda m: " ".join(g for g in m.groups() if g), text)
    return _SPACES.sub(" ", text).strip()


def fold(text: str) -> str:
    """Lowercase and strip accents."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def words(text: str) -> list[str]:
    """Folded words of a text, after name splitting."""
    return [w for w in fold(split_name(text)).split() if w]


def nfc(text: str) -> str:
    """macOS file names come in NFD; everything else is NFC."""
    return unicodedata.normalize("NFC", text)
