"""Text extraction, run in worker processes that are killed when they exceed the timeout."""

from __future__ import annotations

import html
import json
import multiprocessing as mp
import os
import re
import time
import zipfile
from collections import deque
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from multiprocessing.connection import Connection, wait

from .kinds import TEXT_EXTS

_TAG = re.compile(r"<[^>]+>")
_CODE_BLOCKS = re.compile(r"<(style|script|svg|noscript)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


_JUNK = re.compile("[\x00\ue000-\uf8ff\ufffd\ufffe\uffff]")  # NUL, private-use glyphs from PDF fonts, replacement chars


def _clean(text: str) -> str:
    text = _JUNK.sub(" ", text)
    text = _WS.sub(" ", text)
    return _BLANK_LINES.sub("\n\n", text).strip()


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8",):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("cp1252", errors="replace")


def _xml_text(xml: bytes, para_tags: tuple[bytes, ...]) -> str:
    for tag in para_tags:
        xml = xml.replace(tag, b"\n" + tag)
    text = _TAG.sub(" ", xml.decode("utf-8", errors="replace"))
    return html.unescape(text)


def _text_file(path: str, ext: str, limit: int) -> str:
    with open(path, "rb") as f:
        data = f.read(limit * 4)
    if b"\x00" in data[:4096] and data[:2] not in (b"\xff\xfe", b"\xfe\xff"):
        return ""  # binary
    text = _decode(data)
    if ext == "ipynb":
        try:
            nb = json.loads(text)
            text = "\n\n".join("".join(c.get("source", "")) for c in nb.get("cells", []))
        except ValueError:
            pass
    elif ext in ("html", "htm", "xml", "svg"):
        text = html.unescape(_TAG.sub(" ", _CODE_BLOCKS.sub(" ", text)))
    return text


def _pdf(path: str, limit: int) -> str:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(path)
    try:
        out, total = [], 0
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            t = tp.get_text_range()
            tp.close()
            page.close()
            out.append(t)
            total += len(t)
            if total >= limit:
                break
        return "\n\n".join(out)
    finally:
        pdf.close()


def _zip_xml(path: str, members: list[str], para_tags: tuple[bytes, ...]) -> str:
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        return "\n\n".join(_xml_text(z.read(m), para_tags) for m in members if m in names)


def _docx(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    parts = ["word/document.xml"] + sorted(n for n in names if re.match(r"word/(header|footer|footnotes)\d*\.xml", n))
    return _zip_xml(path, parts, (b"<w:p ", b"<w:p>", b"<w:br"))


def _pptx(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    key = lambda n: int(re.search(r"(\d+)\.xml$", n).group(1))
    slides = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=key)
    notes = sorted((n for n in names if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n)), key=key)
    return _zip_xml(path, slides + notes, (b"<a:p>", b"<a:p "))


def _opendoc(path: str) -> str:
    return _zip_xml(path, ["content.xml"], (b"<text:p", b"<text:h"))


def _sheet(path: str, limit: int) -> str:
    from python_calamine import CalamineWorkbook

    wb = CalamineWorkbook.from_path(path)
    out, total = [], 0
    for name in wb.sheet_names:
        out.append(f"# {name}")
        for row in wb.get_sheet_by_name(name).iter_rows():
            line = "\t".join(str(c) for c in row if c not in ("", None))
            if line:
                out.append(line)
                total += len(line)
            if total >= limit:
                return "\n".join(out)
    return "\n".join(out)


def _email(path: str, ext: str) -> str:
    with open(path, "rb") as f:
        data = f.read(4_000_000)
    if ext == "emlx":
        data = data.split(b"\n", 1)[1] if b"\n" in data else data
    msg = BytesParser(policy=policy.default).parsebytes(data)
    head = "\n".join(f"{h}: {msg[h]}" for h in ("Subject", "From", "To", "Date") if msg[h])
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body else ""
    if body and body.get_content_type() == "text/html":
        text = html.unescape(_TAG.sub(" ", text))
    return head + "\n\n" + text


def _rtf(path: str, limit: int) -> str:
    with open(path, "rb") as f:
        data = f.read(limit * 4).decode("cp1252", errors="replace")
    data = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252", "replace"), data)
    data = re.sub(r"\\[a-z]+-?\d* ?|[{}]", " ", data)
    return data


def _epub(path: str, limit: int) -> str:
    out, total = [], 0
    with zipfile.ZipFile(path) as z:
        for n in sorted(z.namelist()):
            if n.endswith((".xhtml", ".html", ".htm")):
                t = html.unescape(_TAG.sub(" ", z.read(n).decode("utf-8", "replace")))
                out.append(t)
                total += len(t)
                if total >= limit:
                    break
    return "\n\n".join(out)


def extract(path: str, ext: str, limit: int) -> str:
    """Plain text of a file, at most `limit` characters. Raises on unreadable files."""
    if ext in TEXT_EXTS:
        text = _text_file(path, ext, limit)
    elif ext == "pdf":
        text = _pdf(path, limit)
    elif ext == "docx":
        text = _docx(path)
    elif ext == "pptx":
        text = _pptx(path)
    elif ext in ("xlsx", "xlsm", "ods"):
        text = _sheet(path, limit)
    elif ext in ("odt", "odp"):
        text = _opendoc(path)
    elif ext in ("eml", "emlx"):
        text = _email(path, ext)
    elif ext == "rtf":
        text = _rtf(path, limit)
    elif ext == "epub":
        text = _epub(path, limit)
    else:
        return ""
    return _clean(text)[:limit]


# ── Worker pool ─────────────────────────────────────────────────────────────


@dataclass
class Result:
    key: int
    text: str
    status: str  # ok, empty, error, timeout
    error: str | None = None


def _worker(conn: Connection) -> None:
    try:
        os.nice(10)
    except OSError:
        pass
    while True:
        task = conn.recv()
        if task is None:
            return
        key, path, ext, limit = task
        try:
            text = extract(path, ext, limit)
            conn.send(Result(key, text, "ok" if text.strip() else "empty"))
        except Exception as e:  # noqa: BLE001 - any parser failure is recorded, never raised
            conn.send(Result(key, "", "error", f"{type(e).__name__}: {e}"[:300]))


class ExtractPool:
    """N worker processes. A task that runs past the timeout gets its worker killed and replaced."""

    def __init__(self, workers: int, timeout: float):
        self.ctx = mp.get_context("spawn")
        self.timeout = timeout
        self.workers: list[dict] = [self._spawn() for _ in range(workers)]

    def _spawn(self) -> dict:
        parent, child = self.ctx.Pipe()
        proc = self.ctx.Process(target=_worker, args=(child,), daemon=True)
        proc.start()
        child.close()
        return {"proc": proc, "conn": parent, "task": None, "started": 0.0}

    def map(self, tasks):
        """tasks: iterable of (key, path, ext, limit). Yields Results in completion order."""
        queue = deque(tasks)
        while queue or any(w["task"] for w in self.workers):
            for w in self.workers:
                if w["task"] is None and queue:
                    w["task"] = queue.popleft()
                    w["started"] = time.monotonic()
                    w["conn"].send(w["task"])
            busy = [w for w in self.workers if w["task"]]
            ready = wait([w["conn"] for w in busy], timeout=0.5)
            now = time.monotonic()
            for i, w in enumerate(self.workers):
                if not w["task"]:
                    continue
                if w["conn"] in ready:
                    try:
                        res = w["conn"].recv()
                    except EOFError:
                        res = Result(w["task"][0], "", "error", "worker exited")
                        self._replace(i)
                    w = self.workers[i]
                    w["task"] = None
                    yield res
                elif now - w["started"] > self.timeout or not w["proc"].is_alive():
                    key = w["task"][0]
                    self._replace(i)
                    yield Result(key, "", "timeout", f"no result after {self.timeout:.0f} s")

    def _replace(self, i: int) -> None:
        w = self.workers[i]
        w["proc"].kill()
        w["proc"].join(1)
        w["conn"].close()
        self.workers[i] = self._spawn()

    def close(self) -> None:
        for w in self.workers:
            try:
                w["conn"].send(None)
            except OSError:
                pass
            w["proc"].join(1)
            if w["proc"].is_alive():
                w["proc"].kill()
