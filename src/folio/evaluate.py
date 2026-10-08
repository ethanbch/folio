"""Ranking evaluation: MRR, recall@1/3/10 and latency over a JSONL file of queries.

Each line: {"query": "...", "expected": ["/abs/path", ...]}. Paths may start with "~".
The default file lives in the data folder, outside the repository: it names real files.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import sys
import time
from dataclasses import fields, replace
from pathlib import Path

from . import db
from .config import data_path, load_config
from .engine import Engine, Options, display_parent

PRESETS: dict[str, list[tuple[str, dict]]] = {
    "phases": [
        ("1 · keywords, names and folders", {"semantic": False, "content": False, "parse": False, "signals": False}),
        ("2 · keywords + content", {"semantic": False, "parse": False, "signals": False}),
        ("3 · hybrid (RRF)", {"parse": False, "signals": False}),
        ("4 · + dates and types", {"signals": False}),
        ("4 · + signals", {}),
        ("4 · + reranker", {"rerank": True}),
    ],
    "weights": [
        ("default", {}),
        ("meaning only", {"lexical": False}),
        ("keywords only", {"semantic": False}),
        ("w_sem 0.5", {"w_sem": 0.5}),
        ("w_sem 1.5", {"w_sem": 1.5}),
        ("w_sem 2", {"w_sem": 2.0}),
        ("rrf_k 60", {"rrf_k": 60.0}),
        ("w_name 5", {"w_name": 5.0}),
        ("w_path 3", {"w_path": 3.0}),
        ("w_content 0.5", {"w_content": 0.5}),
        ("no name vectors", {"name_vectors": False}),
        ("keywords in one list", {"split_lexical": False}),
        ("content keywords ×0.5", {"w_lex_content": 0.5}),
        ("content keywords ×1.5", {"w_lex_content": 1.5}),
        ("rrf_k 10", {"rrf_k": 10.0}),
        ("rrf_k 40", {"rrf_k": 40.0}),
        ("no multi-chunk bonus", {"multi_chunk_bonus": 0.0}),
        ("no recency", {"recency": 0.0, "last_used": 0.0}),
        ("recency ×2", {"recency": 0.3, "last_used": 0.3}),
        ("no exact name", {"exact_name": 0.0}),
        ("exact name 0.6", {"exact_name": 0.6}),
    ],
    "rerank": [
        ("no reranker", {}),
        ("top 20, 600 chars", {"rerank": True, "rerank_top": 20, "rerank_chars": 600}),
        ("top 20, 300 chars", {"rerank": True, "rerank_top": 20, "rerank_chars": 300}),
        ("top 10, 300 chars", {"rerank": True, "rerank_top": 10, "rerank_chars": 300}),
        ("top 10, 150 chars", {"rerank": True, "rerank_top": 10, "rerank_chars": 150}),
        ("top 10, 150 chars, weight 0.5", {"rerank": True, "rerank_weight": 0.5}),
        ("top 10, 150 chars, weight 2", {"rerank": True, "rerank_weight": 2.0}),
    ],
}


def queries_file(arg: str | None) -> Path:
    return Path(arg) if arg else data_path("queries.jsonl")


def load_queries(path: Path) -> list[dict]:
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            q = json.loads(line)
            q["expected"] = [os.path.expanduser(p) for p in q["expected"]]
            out.append(q)
    return out


def _parse_variant(spec: str) -> tuple[str, dict]:
    name, _, kv = spec.partition("=")
    known = {f.name: f.type for f in fields(Options)}
    vals = {}
    for part in filter(None, kv.split(",")):
        k, _, v = part.partition(":")
        if k not in known:
            raise SystemExit(f"Unknown option {k!r}. Options: {', '.join(known)}")
        vals[k] = v.lower() in ("1", "true", "yes", "on") if known[k] == "bool" else float(v) if known[k] == "float" else int(v)
    return name, vals


def evaluate(engine: Engine, queries: list[dict], opts: Options) -> dict:
    by_path = {m.path: m.id for m in engine.catalog.files.values()}
    rr, r1, r3, r10, lat, misses, skipped = [], 0, 0, 0, [], [], 0
    for q in queries:
        expected = {by_path[p] for p in q["expected"] if p in by_path}
        if not expected:
            skipped += 1
            continue
        t0 = time.perf_counter()
        res = engine.search(q["query"], replace(opts, limit=max(10, opts.limit)))
        lat.append((time.perf_counter() - t0) * 1000)
        ids = [h.id for h in res["hits"]]
        rank = next((i for i, fid in enumerate(ids) if fid in expected), None)
        rr.append(1 / (rank + 1) if rank is not None else 0.0)
        r1 += rank is not None and rank < 1
        r3 += rank is not None and rank < 3
        r10 += rank is not None and rank < 10
        if rank is None or rank >= 3:
            got = [engine.catalog.files[i] for i in ids[:3]]
            misses.append(
                {"query": q["query"], "rank": rank, "expected": q["expected"][0], "got": [f"{m.name}  ({display_parent(m)})" for m in got]}
            )
    n = len(rr)
    lat.sort()
    pct = lambda p: lat[min(n - 1, int(p * n))] if n else 0.0
    return {
        "n": n,
        "skipped": skipped,
        "mrr": sum(rr) / n if n else 0.0,
        "r1": r1 / n if n else 0.0,
        "r3": r3 / n if n else 0.0,
        "r10": r10 / n if n else 0.0,
        "p50": statistics.median(lat) if lat else 0.0,
        "p95": pct(0.95),
        "misses": misses,
    }


def run_eval(args) -> int:
    path = queries_file(args.queries)
    if not path.exists():
        print(f"No queries at {path}. Write them with `folio sample`, or pass --queries.", file=sys.stderr)
        return 1
    queries = load_queries(path)
    cfg = load_config()
    engine = Engine(cfg)
    variants = list(PRESETS[args.preset]) if args.preset else []
    variants += [_parse_variant(v) for v in args.variant]
    if not variants:
        variants = [("default", {"rerank": cfg.rerank})]
    # Warm up: model sessions and caches.
    for q in queries[:3]:
        engine.search(q["query"], Options(rerank=any(v.get("rerank") for _, v in variants)))
    rows = []
    for name, vals in variants:
        res = evaluate(engine, queries, Options(**vals))
        rows.append((name, res))
        print(
            f"{name:32} MRR {res['mrr']:.3f}  R@1 {res['r1']:.0%}  R@3 {res['r3']:.0%}  R@10 {res['r10']:.0%}  "
            f"p50 {res['p50']:.0f} ms  p95 {res['p95']:.0f} ms",
            file=sys.stderr,
        )
    if args.markdown:
        print(f"\n{len(queries)} queries ({rows[0][1]['n']} evaluated), {time.strftime('%Y-%m-%d')}.\n")
        print("| Variant | MRR | R@1 | R@3 | R@10 | p50 | p95 |")
        print("| --- | --- | --- | --- | --- | --- | --- |")
        for name, r in rows:
            print(f"| {name} | {r['mrr']:.3f} | {r['r1']:.0%} | {r['r3']:.0%} | {r['r10']:.0%} | {r['p50']:.0f} ms | {r['p95']:.0f} ms |")
    if rows[0][1]["skipped"]:
        print(f"{rows[0][1]['skipped']} queries skipped: expected file not in the index.", file=sys.stderr)
    if args.failures:
        name, r = rows[-1]
        print(f"\nOutside the top 3 ({name}):", file=sys.stderr)
        for m in r["misses"]:
            print(
                f"- {m['query']!r}: rank {m['rank'] + 1 if m['rank'] is not None else '> 30'}, expected {Path(m['expected']).name}",
                file=sys.stderr,
            )
            for g in m["got"]:
                print(f"    {g}", file=sys.stderr)
    return 0


# ── Building the query set ──────────────────────────────────────────────────

SENSITIVE = (
    "paie",
    "salaire",
    "bulletin",
    "impot",
    "impôt",
    "fiscal",
    "banque",
    "bancaire",
    "releve",
    "relevé",
    "rib",
    "iban",
    "passeport",
    "passport",
    "identite",
    "identité",
    "cni",
    "permis",
    "carte vitale",
    "secu",
    "sécu",
    "medical",
    "médical",
    "ordonnance",
    "sante",
    "santé",
    "mutuelle",
    "importants",
    "billets",
    "billet",
    "password",
    "mot de passe",
    "contrat de travail",
    "avis d'imposition",
    "quittance",
    "bail",
    "caf",
    "pole emploi",
    "france travail",
    "urssaf",
    "naissance",
    "acte",
)


def is_sensitive(path: str) -> bool:
    low = path.lower()
    return any(s in low for s in SENSITIVE)


def sample(args) -> int:
    """Print a varied sample of indexed files (non-sensitive), with a content excerpt, as JSONL."""
    cfg = load_config()
    engine = Engine(cfg, load_models=False)
    rows = db.connect().execute("SELECT id, path, kind, status FROM files").fetchall()
    rnd = random.Random(args.seed)
    pool = [r for r in rows if not is_sensitive(r["path"])]
    by_kind: dict[str, list] = {}
    for r in pool:
        by_kind.setdefault((r["kind"], r["status"] == "ok"), []).append(r)
    picked = []
    keys = sorted(by_kind, key=lambda k: -len(by_kind[k]))
    while len(picked) < args.n and any(by_kind.values()):
        for k in keys:
            if by_kind[k] and len(picked) < args.n:
                picked.append(by_kind[k].pop(rnd.randrange(len(by_kind[k]))))
    for r in picked:
        m = engine.catalog.files[r["id"]]
        content = engine.lexical.content(r["id"])[:400].replace("\n", " ") if r["status"] == "ok" else ""
        print(json.dumps({"path": m.path.replace(str(Path.home()), "~"), "kind": m.kind, "content": content}, ensure_ascii=False))
    return 0


def export_log(args) -> int:
    """Queries followed by an open or reveal become evaluation queries."""
    rows = (
        db.connect()
        .execute(
            "SELECT query, path, MAX(ts) FROM clicks WHERE action IN ('open', 'reveal', 'copy') AND query != '' GROUP BY query, path ORDER BY 3"
        )
        .fetchall()
    )
    out = Path(args.out) if args.out else data_path("queries-from-log.jsonl")
    with open(out, "w") as f:
        for q, path, _ in rows:
            f.write(json.dumps({"query": q, "expected": [path.replace(str(Path.home()), "~")], "source": "log"}, ensure_ascii=False) + "\n")
    print(f"{len(rows)} queries written to {out}")
    return 0
