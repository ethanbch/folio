"""Split extracted text into overlapping chunks for embedding."""

from __future__ import annotations

import re

from .textnorm import split_name

# ≈ 250 tokens of French text for the e5 tokenizer (measured: ≈ 4.5 characters per token).
CHUNK_CHARS = 1100
OVERLAP_CHARS = 180

_BREAK = re.compile(r"(?<=[.!?…:;])\s+|\n+")


def chunks(text: str, max_chunks: int, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[tuple[int, int]]:
    """(start, end) character spans, cut at sentence or line ends when possible."""
    spans: list[tuple[int, int]] = []
    n, start = len(text), 0
    while start < n and len(spans) < max_chunks:
        end = min(n, start + size)
        if end < n:
            window = text[start + size // 2 : end]
            breaks = [m.end() for m in _BREAK.finditer(window)]
            if breaks:
                end = start + size // 2 + breaks[-1]
            else:
                space = text.rfind(" ", start + size // 2, end)
                end = space if space > start else end
        if text[start:end].strip():
            spans.append((start, end))
        if end >= n:
            break
        start = max(end - overlap, start + 1)
        # Start on a word boundary.
        nxt = text.find(" ", start, end)
        start = nxt + 1 if 0 <= nxt < end else start
    return spans


def context_label(name: str, rel_parent: str) -> str:
    """Readable label for a file: its name and the last folders above it."""
    folders = [split_name(p) for p in rel_parent.split("/") if p][-3:]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    label = split_name(stem)
    return f"{label} — {' / '.join(folders)}" if folders else label


def passage(name: str, rel_parent: str, body: str) -> str:
    return f"{context_label(name, rel_parent)}\n{body}"
