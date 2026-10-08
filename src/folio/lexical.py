"""Lexical index (tantivy): one document per file, with name, folder and content fields."""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass

import tantivy

from .config import data_path
from .textnorm import split_name, words

SCHEMA_VERSION = "4"

# French and English words that carry no meaning in a file search.
STOPWORDS = {
    "le",
    "la",
    "les",
    "l",
    "un",
    "une",
    "des",
    "de",
    "du",
    "d",
    "au",
    "aux",
    "et",
    "ou",
    "a",
    "en",
    "dans",
    "sur",
    "pour",
    "par",
    "avec",
    "sans",
    "mon",
    "ma",
    "mes",
    "ton",
    "ta",
    "tes",
    "son",
    "sa",
    "ses",
    "ce",
    "cet",
    "cette",
    "ces",
    "qui",
    "que",
    "quoi",
    "j",
    "je",
    "tu",
    "il",
    "elle",
    "on",
    "nous",
    "vous",
    "y",
    "ai",
    "est",
    "fichier",
    "fichiers",
    "doc",
    "document",
    "the",
    "of",
    "and",
    "or",
    "in",
    "for",
    "to",
    "my",
    "file",
    "files",
    "with",
    "an",
    "trouve",
    "trouver",
    "cherche",
    "chercher",
    "retrouve",
    "retrouver",
    "where",
    "find",
}


@dataclass
class Weights:
    name: float = 3.0
    path: float = 1.5
    content: float = 1.0
    fuzzy: float = 0.4  # multiplier for typo-tolerant matches
    prefix: float = 0.7  # multiplier for the word being typed


def _analyzer() -> tantivy.TextAnalyzer:
    return (
        tantivy.TextAnalyzerBuilder(tantivy.Tokenizer.simple())
        .filter(tantivy.Filter.remove_long(60))
        .filter(tantivy.Filter.lowercase())
        .filter(tantivy.Filter.ascii_fold())
        .filter(tantivy.Filter.stemmer("french"))
        .build()
    )


def _schema() -> tantivy.Schema:
    sb = tantivy.SchemaBuilder()
    sb.add_integer_field("id", stored=True, indexed=True, fast=True)
    sb.add_text_field("name", tokenizer_name="fr")
    sb.add_text_field("path", tokenizer_name="fr")
    sb.add_text_field("content", stored=True, tokenizer_name="fr")
    sb.add_text_field("ext", tokenizer_name="raw")
    return sb.build()


def folder_words(rel_parent: str) -> str:
    """Folder names of a path relative to its root, split into words."""
    return " ".join(split_name(p) for p in rel_parent.split("/") if p)


class LexicalIndex:
    def __init__(self) -> None:
        path = data_path("tantivy")
        stamp = path / "folio-schema"
        if path.exists() and (not stamp.exists() or stamp.read_text() != SCHEMA_VERSION):
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        stamp.write_text(SCHEMA_VERSION)
        self.schema = _schema()
        self.index = tantivy.Index(self.schema, path=str(path))
        self.analyzer = _analyzer()
        self.index.register_tokenizer("fr", self.analyzer)
        self._writer: tantivy.IndexWriter | None = None
        self._lock = threading.Lock()
        self.searcher = self.index.searcher()

    # ── Writing ─────────────────────────────────────────────────────────────

    @property
    def writer(self) -> tantivy.IndexWriter:
        if self._writer is None:
            self._writer = self.index.writer(heap_size=32_000_000, num_threads=1)
        return self._writer

    def upsert(self, file_id: int, name: str, rel_parent: str, ext: str, content: str) -> None:
        with self._lock:
            self.writer.delete_documents_by_term("id", file_id)
            self.writer.add_document(
                tantivy.Document(
                    id=file_id,
                    name=split_name(name),
                    path=folder_words(rel_parent),
                    content=content,
                    ext=ext,
                )
            )

    def delete(self, file_id: int) -> None:
        with self._lock:
            self.writer.delete_documents_by_term("id", file_id)

    def commit(self) -> None:
        with self._lock:
            if self._writer is not None:
                self._writer.commit()
                self._writer.wait_merging_threads()
                self._writer = None
        self.index.reload()
        self.searcher = self.index.searcher()

    def clear(self) -> None:
        with self._lock:
            self.writer.delete_all_documents()
        self.commit()

    # ── Reading ─────────────────────────────────────────────────────────────

    def stems(self, text: str) -> list[str]:
        return self.analyzer.analyze(text)

    def query_terms(self, text: str) -> list[str]:
        """Stemmed query terms, stopwords removed (unless nothing else is left)."""
        ws = words(text)
        kept = [w for w in ws if w not in STOPWORDS] or ws
        out: list[str] = []
        for w in kept:
            for s in self.stems(w):
                if s not in out:
                    out.append(s)
        return out

    def build_query(self, text: str, weights: Weights, exts: set[str] | None = None, prefix_last: bool = True) -> tantivy.Query | None:
        terms = self.query_terms(text)
        if not terms:
            return None
        fields = [("name", weights.name), ("path", weights.path), ("content", weights.content)]
        Q, O = tantivy.Query, tantivy.Occur
        typed_last = prefix_last and text[-1:].isalnum()
        clauses = []
        for i, term in enumerate(terms):
            parts = []
            for field, w in fields:
                if w <= 0:
                    continue
                parts.append((O.Should, Q.boost_query(Q.term_query(self.schema, field, term), w)))
                if len(term) >= 5 and field != "content":
                    fuzzy = Q.fuzzy_term_query(self.schema, field, term, distance=1)
                    parts.append((O.Should, Q.boost_query(fuzzy, w * weights.fuzzy)))
                if typed_last and i == len(terms) - 1 and len(term) >= 2 and field != "content":
                    pre = Q.fuzzy_term_query(self.schema, field, term, distance=0, prefix=True)
                    parts.append((O.Should, Q.boost_query(pre, w * weights.prefix)))
            # One word's best field counts, plus a little for the others.
            clauses.append((O.Should, Q.disjunction_max_query([q for _, q in parts], 0.2)))
        query = Q.boolean_query(clauses)
        if exts:
            ext_q = Q.boolean_query([(O.Should, Q.term_query(self.schema, "ext", e)) for e in sorted(exts)])
            query = Q.boolean_query([(O.Must, query), (O.Must, ext_q)])
        return query

    def search(self, query: tantivy.Query, limit: int) -> list[tuple[int, float]]:
        searcher = self.searcher
        hits = searcher.search(query, limit, count=False).hits
        out = []
        for score, addr in hits:
            doc = searcher.doc(addr)
            out.append((doc["id"][0], score))
        return out

    def content(self, file_id: int) -> str:
        searcher = self.searcher
        q = tantivy.Query.term_query(self.schema, "id", file_id)
        hits = searcher.search(q, 1, count=False).hits
        if not hits:
            return ""
        vals = searcher.doc(hits[0][1]).get_all("content")
        return vals[0] if vals else ""

    def num_docs(self) -> int:
        return self.searcher.num_docs
