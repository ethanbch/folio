"""Search engine: query parsing, lexical and semantic retrieval, fusion, ranking signals, re-ranking."""

from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import db
from .config import ICLOUD_DIR, Config
from .extract import _JUNK
from .lexical import STOPWORDS, LexicalIndex, Weights
from .models import EMBEDDERS, Embedder, Reranker
from .queryparse import Parsed, parse
from .textnorm import fold, split_name
from .vectors import VectorStore

ROOT_ALIASES = {
    "Downloads": "Downloads Téléchargements",
    "Desktop": "Desktop Bureau",
    "Documents": "Documents",
}

# Folders that usually hold copies, old versions or noise.
NOISY_FOLDERS = {
    "archive",
    "archives",
    "old",
    "backup",
    "backups",
    "sauvegarde",
    "tmp",
    "temp",
    "corbeille",
    "trash",
    "copie",
    "copies",
    "anciens",
    "ancien",
}
_DUP_SUFFIX = re.compile(r"(?: \(\d+\)| copie(?: \d+)?| copy(?: \d+)?)\.[^.]+$", re.IGNORECASE)


@dataclass
class Options:
    """Every ranking knob. Defaults are the measured best (docs/EVAL.md)."""

    lexical: bool = True
    semantic: bool = True
    content: bool = True  # search extracted text (lexical and semantic)
    name_vectors: bool = True  # one vector per file for its name and folders
    parse: bool = True  # dates and types
    signals: bool = True
    rerank: bool = False
    w_name: float = 3.0
    w_path: float = 1.5
    w_content: float = 1.0
    w_lex: float = 1.0  # names and folders list
    w_lex_content: float = 1.0  # content list
    split_lexical: bool = False  # measured: one combined list ranks better (docs/EVAL.md)
    w_sem: float = 1.0
    rrf_k: float = 20.0
    multi_chunk_bonus: float = 0.05
    sem_only_margin: float = 0.03  # drop meaning-only hits this far below the best cosine (measured: no loss)
    recency: float = 0.15
    last_used: float = 0.15
    frecency: float = 0.4
    exact_name: float = 0.3
    noisy_folder: float = 0.15
    duplicate: float = 0.1
    year_hint: float = 0.3
    cover: float = 0.3  # share of query words found in the name and folders
    parsed_strict: bool = False  # dates and types from the query: exclude (True) or rank (False)
    date_in: float = 0.4
    date_out: float = 0.2
    type_in: float = 0.4
    type_out: float = 0.2
    rerank_top: int = 10
    rerank_weight: float = 1.0
    rerank_chars: int = 150
    limit: int = 30


@dataclass
class Meta:
    id: int
    path: str
    name: str
    ext: str
    kind: str
    size: int
    mtime: float
    ctime: float
    last_used: float | None
    dataless: bool
    status: str
    root: str = ""
    rel_parent: str = ""


@dataclass
class Hit:
    id: int
    score: float
    reasons: list[str] = field(default_factory=list)
    lex_rank: int | None = None
    sem_rank: int | None = None
    best_row: int | None = None
    debug: dict = field(default_factory=dict)


def split_root(path: str, roots: list[Path]) -> tuple[str, str]:
    """(root label, parent folders relative to the root)."""
    p = Path(path)
    for r in roots:
        if p.is_relative_to(r):
            label = "iCloud Drive" if r == ICLOUD_DIR else r.name
            rel = p.parent.relative_to(r).as_posix()
            return label, "" if rel == "." else rel
    return "", p.parent.as_posix()


def display_parent(meta: Meta) -> str:
    base = "iCloud Drive" if meta.root == "iCloud Drive" else ("~/" + meta.root if meta.root else "")
    return f"{base}/{meta.rel_parent}" if meta.rel_parent else base


class Catalog:
    """File metadata kept in memory for filtering and ranking."""

    def __init__(self, roots: list[Path]):
        self.roots = roots
        self.files: dict[int, Meta] = {}
        self.lock = threading.Lock()
        self.reload()

    def _meta(self, r) -> Meta:
        root, rel = split_root(r["path"], self.roots)
        return Meta(
            r["id"],
            r["path"],
            r["name"],
            r["ext"],
            r["kind"],
            r["size"],
            r["mtime"],
            r["ctime"],
            r["last_used"],
            bool(r["dataless"]),
            r["status"],
            root,
            rel,
        )

    def reload(self) -> None:
        rows = (
            db.connect().execute("SELECT id, path, name, ext, kind, size, mtime, ctime, last_used, dataless, status FROM files").fetchall()
        )
        files = {r["id"]: self._meta(r) for r in rows}
        with self.lock:
            self.files = files
            self._arrays()

    def update(self, ids: list[int]) -> None:
        if not ids:
            return
        conn = db.connect()
        with self.lock:
            for i in range(0, len(ids), 500):
                part = ids[i : i + 500]
                rows = conn.execute(
                    f"SELECT id, path, name, ext, kind, size, mtime, ctime, last_used, dataless, status FROM files WHERE id IN ({','.join('?' * len(part))})",
                    part,
                ).fetchall()
                found = {r["id"] for r in rows}
                for r in rows:
                    self.files[r["id"]] = self._meta(r)
                for fid in part:
                    if fid not in found:
                        self.files.pop(fid, None)
            self._arrays()

    def _arrays(self) -> None:
        n = (max(self.files) + 1) if self.files else 1
        self.exists = np.zeros(n, dtype=bool)
        self.mtime = np.zeros(n)
        self.ctime = np.zeros(n)
        self.used = np.zeros(n)
        self.ext = np.empty(n, dtype=object)
        for m in self.files.values():
            self.exists[m.id] = True
            self.mtime[m.id] = m.mtime
            self.ctime[m.id] = m.ctime
            self.used[m.id] = m.last_used or 0
            self.ext[m.id] = m.ext

    def mask(self, exts: set[str] | None, date_from: float | None, date_to: float | None) -> np.ndarray:
        with self.lock:
            ok = self.exists.copy()
            if exts:
                ok &= np.isin(self.ext, list(exts))
            if date_from is not None:
                in_range = lambda a: (a >= date_from) & (a < date_to)
                ok &= in_range(self.mtime) | in_range(self.used) | in_range(self.ctime)
            return ok


class Engine:
    def __init__(self, cfg: Config, load_models: bool = True):
        self.cfg = cfg
        self.roots = cfg.root_paths
        self.lexical = LexicalIndex()
        spec = EMBEDDERS[cfg.embedding_model]
        self.vectors = VectorStore(spec.dim, spec.key)
        self.catalog = Catalog(self.roots)
        self.embedder: Embedder | None = None
        self._reranker: Reranker | None = None
        self.embed_lock = threading.Lock()
        self.rerank_lock = threading.Lock()
        self.queries_waiting = 0
        if load_models:
            self.load_embedder()
        self.load_owners()
        self.frecency = Frecency()
        self._stem_cache: dict = {}

    def load_embedder(self, allow_download: bool = True) -> Embedder:
        """Load the embedding model (downloading it the first time). Shared by queries and indexing."""
        with self.embed_lock:
            if self.embedder is None:
                self.embedder = Embedder(self.cfg.embedding_model, threads=4, allow_download=allow_download)
            return self.embedder

    def model_ready(self) -> bool:
        from .models import model_dir, vocab_path

        return (model_dir(EMBEDDERS[self.cfg.embedding_model]) / "model.onnx").exists() and vocab_path().exists()

    def load_owners(self) -> None:
        rows = db.connect().execute("SELECT row, file_id FROM chunks").fetchall()
        self.vectors.set_owners((r[0], r[1]) for r in rows)

    @property
    def reranker(self) -> Reranker:
        return self.load_reranker()

    @property
    def reranker_ready(self) -> bool:
        return self._reranker is not None

    def load_reranker(self, allow_download: bool = True) -> Reranker:
        with self.rerank_lock:
            if self._reranker is None:
                self._reranker = Reranker(threads=4, allow_download=allow_download)
            return self._reranker

    def embed_query(self, text: str) -> np.ndarray:
        self.queries_waiting += 1  # indexing yields the model to queries (see Indexer._index_one)
        try:
            with self.embed_lock:
                return self.embedder.embed_query(text)
        finally:
            self.queries_waiting -= 1

    # ── Search ──────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        opts: Options | None = None,
        disabled: set[str] | None = None,
        exts: set[str] | None = None,
        since: float | None = None,
    ) -> dict:
        """exts, since: filters picked in the interface (strict). Dates and types read from the
        query rank matching files higher (soft), unless opts.parsed_strict."""
        t0 = time.perf_counter()
        opts = opts or Options(rerank=self.cfg.rerank)
        parsed = parse(query, disabled=disabled) if opts.parse else Parsed(text=query.strip())
        text = parsed.text
        hard_exts = set(exts) if exts else set()
        hard_from, hard_to = (since, time.time() + 86400) if since else (None, None)
        relaxed = False
        if opts.parsed_strict:
            hits = self._retrieve(text, parsed, opts, *self._merge_hard(parsed, hard_exts, hard_from, hard_to), soft=False)
            if len(hits) < 3 and (parsed.date_from is not None or parsed.exts):
                more = self._retrieve(text, parsed, opts, hard_exts, hard_from, hard_to, soft=True)
                seen = {h.id for h in hits}
                hits += [h for h in more if h.id not in seen]
                relaxed = True
        else:
            hits = self._retrieve(text, parsed, opts, hard_exts, hard_from, hard_to, soft=True)
        hits = hits[: max(opts.limit, opts.rerank_top)]
        t_fast = (time.perf_counter() - t0) * 1000
        if opts.rerank and text and len(hits) > 1:
            hits = self._rerank(text, hits, opts)
        hits = hits[: opts.limit]
        ms = (time.perf_counter() - t0) * 1000
        return {"parsed": parsed, "hits": hits, "relaxed": relaxed, "ms": ms, "ms_fast": t_fast}

    @staticmethod
    def _merge_hard(parsed: Parsed, exts: set[str], date_from, date_to):
        if parsed.exts:
            exts = (exts & parsed.exts) or parsed.exts if exts else set(parsed.exts)
        if parsed.date_from is not None:
            date_from = max(date_from or 0, parsed.date_from)
            date_to = min(date_to, parsed.date_to) if date_to else parsed.date_to
        return exts, date_from, date_to

    def _retrieve(self, text: str, parsed: Parsed, opts: Options, exts: set[str], date_from, date_to, soft: bool) -> list[Hit]:
        allowed = self.catalog.mask(exts, date_from, date_to)
        files = self.catalog.files

        if not text.strip():
            # Filters only: the parsed filters become strict, newest first.
            exts2, from2, to2 = self._merge_hard(parsed, exts, date_from, date_to)
            allowed = self.catalog.mask(exts2, from2, to2)
            ids = np.where(allowed)[0]
            ids = sorted(ids, key=lambda i: -files[i].mtime)[: opts.limit]
            return [Hit(int(i), 1.0 / (r + 1)) for r, i in enumerate(ids)]

        # Keywords: names and folders in one list, content in another. Separate lists keep files known
        # only by name (iCloud placeholders, images) from being buried under files with text.
        lex_lists: list[tuple[str, float, list[tuple[int, float]]]] = []
        if opts.lexical:
            lex_text = f"{text} {parsed.name_terms}".strip()
            plans = [("names", opts.w_lex, Weights(name=opts.w_name, path=opts.w_path, content=0.0))]
            if opts.content:
                if opts.split_lexical:
                    plans.append(("content", opts.w_lex_content, Weights(name=0.0, path=0.0, content=1.0)))
                else:
                    plans[0] = ("names", opts.w_lex, Weights(name=opts.w_name, path=opts.w_path, content=opts.w_content))
            for key, weight, w in plans:
                q = self.lexical.build_query(lex_text, w, exts or None, prefix_last=key == "names")
                if q is not None:
                    found = [(fid, s) for fid, s in self.lexical.search(q, 200) if fid < len(allowed) and allowed[fid]]
                    lex_lists.append((key, weight, found))

        sem: list[tuple[int, float, int, int]] = []  # file, best score, best row, matching rows
        if opts.semantic and self.embedder is not None and self.vectors.rows:
            qv = self.embed_query(text)
            rows = self.vectors.search(qv, 300, allowed)
            best: dict[int, list] = {}
            for row, fid, score in rows:
                if not opts.name_vectors and self._is_name_row(row):
                    continue
                if not opts.content and not self._is_name_row(row):
                    continue
                b = best.get(fid)
                if b is None:
                    best[fid] = [score, row, 1]
                elif score > b[0] - 0.02:
                    b[2] += 1
            sem = sorted(((f, b[0], b[1], b[2]) for f, b in best.items()), key=lambda x: -x[1])[:150]

        hits: dict[int, Hit] = {}
        for key, weight, found in lex_lists:
            for rank, (fid, s) in enumerate(found):
                if fid not in files:
                    continue
                h = hits.setdefault(fid, Hit(fid, 0.0))
                h.lex_rank = rank if h.lex_rank is None else min(h.lex_rank, rank)
                h.score += weight / (opts.rrf_k + rank + 1)
                h.debug[key] = (rank, round(s, 2))
        for rank, (fid, s, row, n) in enumerate(sem):
            if fid not in files:
                continue
            h = hits.setdefault(fid, Hit(fid, 0.0))
            h.sem_rank = rank
            h.best_row = row
            bonus = 1 + opts.multi_chunk_bonus * min(n - 1, 5)
            h.score += opts.w_sem * bonus / (opts.rrf_k + rank + 1)
            h.debug["cos"] = round(s, 3)

        # Files found only by meaning, far below the best match, are noise ("gratin" for "devis cuisine").
        if sem and opts.sem_only_margin > 0:
            floor = sem[0][1] - opts.sem_only_margin
            for fid, cos, _, _ in sem:
                h = hits.get(fid)
                if h is not None and h.lex_rank is None and cos < floor:
                    del hits[fid]
        self._signals(text, parsed, list(hits.values()), opts, soft)
        return sorted(hits.values(), key=lambda h: -h.score)

    def _file_stems(self, m: Meta) -> tuple[set[str], set[str]]:
        """Stems of a file's name and of its folders, cached."""
        key = (m.id, m.path)
        cached = self._stem_cache.get(key)
        if cached is None:
            name = set(self.lexical.stems(split_name(m.name.rsplit(".", 1)[0])))
            folders = set(self.lexical.stems(split_name(m.rel_parent.replace("/", " ")) + " " + ROOT_ALIASES.get(m.root, m.root)))
            cached = (name, folders)
            if len(self._stem_cache) > 50_000:
                self._stem_cache.clear()
            self._stem_cache[key] = cached
        return cached

    def _is_name_row(self, row: int) -> bool:
        return row in self._name_rows

    @property
    def _name_rows(self) -> set[int]:
        # Rows whose chunk spans (0, 0) are name vectors. Cached per vector-store size.
        key = (self.vectors.rows, len(self.vectors.owner))
        if getattr(self, "_name_rows_key", None) != key:
            rows = db.connect().execute("SELECT row FROM chunks WHERE start = 0 AND end = 0").fetchall()
            self._name_rows_cache = {r[0] for r in rows}
            self._name_rows_key = key
        return self._name_rows_cache

    def _signals(self, text: str, parsed: Parsed, hits: list[Hit], opts: Options, soft: bool) -> None:
        now = time.time()
        q_words = {w for w in fold(split_name(text)).split() if w not in STOPWORDS}
        q_stems = set(self.lexical.query_terms(text))
        clicks = self.frecency.scores(text) if opts.signals else ({}, {})
        for h in hits:
            m = self.catalog.files[h.id]
            bonus = 0.0
            if opts.signals:
                age_days = max(0.0, (now - m.mtime) / 86400)
                bonus += opts.recency * math.exp(-age_days / 120)
                if m.last_used:
                    bonus += opts.last_used * math.exp(-max(0.0, now - m.last_used) / 86400 / 60)
                if parsed.recent:
                    bonus += 0.5 * math.exp(-age_days / 30)
                name_stems, folder_stems = self._file_stems(m)
                if q_stems and q_stems <= name_stems:
                    bonus += opts.exact_name
                    h.debug["exact"] = True
                elif q_words and q_words <= set(fold(split_name(m.name)).split()):
                    bonus += opts.exact_name
                if q_stems and opts.cover:
                    cover = len(q_stems & (name_stems | folder_stems)) / len(q_stems)
                    bonus += opts.cover * cover
                folders = {fold(p) for p in m.rel_parent.split("/")}
                if folders & NOISY_FOLDERS and not (folders & q_words):
                    bonus -= opts.noisy_folder
                if _DUP_SUFFIX.search(m.name):
                    bonus -= opts.duplicate
                depth = m.rel_parent.count("/") + 1 if m.rel_parent else 0
                if depth > 6:
                    bonus -= 0.02 * (depth - 6)
                if parsed.year_hint:
                    y = str(parsed.year_hint)
                    in_year = time.localtime(m.mtime).tm_year == parsed.year_hint
                    if y in m.name or y in m.rel_parent or in_year:
                        bonus += opts.year_hint
                general, specific = clicks
                f = opts.frecency * (general.get(h.id, 0.0) + 3 * specific.get(h.id, 0.0))
                if f:
                    bonus += min(opts.frecency, f)
                    h.debug["frecency"] = round(f, 2)
            if soft:
                if parsed.date_from is not None:
                    ts = (m.mtime, m.last_used or 0, m.ctime)
                    in_range = any(parsed.date_from <= t < parsed.date_to for t in ts)
                    if parsed.name_terms and parsed.name_terms.replace(" ", "") in m.name.replace("_", "").replace("-", ""):
                        in_range = True
                    bonus += opts.date_in if in_range else -opts.date_out
                if parsed.exts:
                    bonus += opts.type_in if m.ext in parsed.exts else -opts.type_out
            h.score *= max(0.05, 1 + bonus)
            h.debug["bonus"] = round(bonus, 3)

    def _rerank(self, text: str, hits: list[Hit], opts: Options) -> list[Hit]:
        top = hits[: opts.rerank_top]
        passages = [self.rerank_passage(h, opts.rerank_chars) for h in top]
        scores = self.reranker.score(text, passages)
        # Blend: reranker probability with the fused rank, so a confident first stage is kept.
        probs = 1 / (1 + np.exp(-scores))
        for rank, (h, p) in enumerate(zip(top, probs)):
            h.debug["rerank"] = round(float(p), 3)
            h.score = opts.rerank_weight * float(p) + 1.0 / (rank + 2)
        top.sort(key=lambda h: -h.score)
        return top + hits[opts.rerank_top :]

    def rerank_passage(self, h: Hit, chars: int = 150) -> str:
        m = self.catalog.files[h.id]
        head = f"{m.name} — {display_parent(m)}"
        body = self.chunk_text(h.best_row) if h.best_row is not None else ""
        if not body and m.status == "ok":
            body = self.lexical.content(h.id)[:chars]
        return f"{head}\n{body[:chars]}"

    def chunk_text(self, row: int) -> str:
        r = db.connect().execute("SELECT file_id, start, end FROM chunks WHERE row=?", (row,)).fetchone()
        if not r or r["end"] == 0:
            return ""
        return self.lexical.content(r["file_id"])[r["start"] : r["end"]]

    # ── Presentation ────────────────────────────────────────────────────────

    def explain(self, text: str, h: Hit) -> list[str]:
        if not text.strip():
            return []
        m = self.catalog.files[h.id]
        stems = set(self.lexical.query_terms(text))
        reasons = []
        if stems & set(self.lexical.stems(split_name(m.name))):
            reasons.append("name")
        parent_words = split_name(m.rel_parent.replace("/", " ")) + " " + ROOT_ALIASES.get(m.root, m.root)
        if stems & set(self.lexical.stems(parent_words)):
            reasons.append("folder")
        if h.lex_rank is not None and not reasons and m.status == "ok":
            reasons.append("content")
        if h.sem_rank is not None and h.sem_rank < 10:
            reasons.append("meaning")
        if h.debug.get("frecency"):
            reasons.append("history")
        return reasons

    def word_pattern(self, text: str) -> re.Pattern | None:
        """Accent- and case-insensitive regex matching words that start with a query stem."""
        stems = [s for s in self.lexical.query_terms(text) if len(s) >= 2]
        if not stems:
            return None
        alts = "|".join(sorted(("".join(_ACCENTS.get(c, re.escape(c)) for c in s) for s in stems), key=len, reverse=True))
        # Word boundaries ignore "_" so that "ACME_Gouvernance" and "risques_Epdf" split like words.
        return re.compile(rf"(?<![^\W_])(?:{alts})[^\W_]*", re.IGNORECASE)

    def snippet(self, text: str, h: Hit, pattern: re.Pattern | None, size: int = 220) -> tuple[str, list[tuple[int, int]]]:
        """An excerpt of the content with highlight ranges for query words."""
        m = self.catalog.files[h.id]
        if m.status != "ok":
            return "", []
        content = self.lexical.content(h.id)
        if not content:
            return "", []
        start = None
        if h.best_row is not None and (h.lex_rank is None or (h.sem_rank is not None and h.sem_rank < h.lex_rank)):
            r = db.connect().execute("SELECT start, end FROM chunks WHERE row=?", (h.best_row,)).fetchone()
            if r and r["end"]:
                start = r["start"]
        if start is None and pattern is not None:
            wm = pattern.search(content)
            if wm:
                start = max(0, wm.start() - size // 3)
        start = start or 0
        if start:
            sp = content.find(" ", start)
            start = sp + 1 if 0 <= sp < start + 30 else start
        excerpt = content[start : start + size]
        cut = excerpt.rfind(" ")
        more = start + size < len(content)
        if more and cut > size * 0.7:
            excerpt = excerpt[:cut]
        excerpt = re.sub(r"\s+", " ", _JUNK.sub(" ", excerpt)).strip()
        prefix = "… " if start > 0 else ""
        ranges = [(a.start() + len(prefix), a.end() + len(prefix)) for a in pattern.finditer(excerpt)] if pattern else []
        return prefix + excerpt + (" …" if more else ""), ranges


_ACCENTS = {
    "a": "[aàâäáã]",
    "e": "[eéèêë]",
    "i": "[iîïíì]",
    "o": "[oôöóòõ]",
    "u": "[uùûüú]",
    "c": "[cç]",
    "y": "[yÿ]",
    "n": "[nñ]",
}


class Frecency:
    """Clicks from the UI, decayed over time. Read from SQLite, cached for a minute."""

    def __init__(self):
        self._cache: tuple[float, dict[int, float], list] | None = None

    def _load(self):
        now = time.time()
        if self._cache and now - self._cache[0] < 60:
            return self._cache
        rows = db.connect().execute("SELECT ts, query, file_id FROM clicks WHERE ts > ?", (now - 365 * 86400,)).fetchall()
        general: dict[int, float] = {}
        for r in rows:
            general[r["file_id"]] = general.get(r["file_id"], 0.0) + 0.3 * math.exp(-(now - r["ts"]) / 86400 / 30)
        self._cache = (now, general, [(fold(r["query"]).strip(), r["file_id"], r["ts"]) for r in rows])
        return self._cache

    def invalidate(self) -> None:
        self._cache = None

    def scores(self, query: str) -> tuple[dict[int, float], dict[int, float]]:
        _, general, rows = self._load()
        q = fold(query).strip()
        specific: dict[int, float] = {}
        if q:
            for rq, fid, _ts in rows:
                if rq == q or (len(q) >= 4 and rq.startswith(q)):
                    specific[fid] = specific.get(fid, 0.0) + 0.5
        return general, specific
