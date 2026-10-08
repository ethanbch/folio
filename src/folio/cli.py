"""Command line: folio serve | index | reindex | search | eval | doctor | agent | models."""

from __future__ import annotations

import argparse
import json
import sys
import time


def _server_running(cfg) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{cfg.port}/api/ping", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def _ask_server(cfg, full: bool) -> bool:
    """Ask a running server to index (it owns the index writer)."""
    import urllib.request

    from .config import data_path

    token_file = data_path("server.token")
    if not token_file.exists():
        return False
    req = urllib.request.Request(
        f"http://127.0.0.1:{cfg.port}/api/index",
        data=json.dumps({"full": full}).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Folio-Token": token_file.read_text().strip(),
            "Origin": f"http://127.0.0.1:{cfg.port}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 202
    except OSError:
        return False


def cmd_index(args, full: bool = False) -> int:
    from .config import load_config

    cfg = load_config()
    if _server_running(cfg):
        if _ask_server(cfg, full):
            print("The running server started indexing. Follow progress on its status page.")
            return 0
        print("A folio server is running but did not accept the request. Stop it, or use its status page.", file=sys.stderr)
        return 1
    from .engine import Engine
    from .indexer import Indexer

    engine = Engine(cfg, load_models=False)
    idx = Indexer(engine, cfg)
    t0 = time.time()

    import threading

    done = threading.Event()

    def report():
        while not done.wait(2):
            p = idx.progress
            if p.total:
                print(f"\r{p.message}: {p.done}/{p.total}  ({time.time() - t0:.0f} s)   ", end="", file=sys.stderr, flush=True)
            else:
                print(f"\r{p.message} ({time.time() - t0:.0f} s)   ", end="", file=sys.stderr, flush=True)

    threading.Thread(target=report, daemon=True).start()
    try:
        stats = idx.run(full=full)
    finally:
        done.set()
    print(file=sys.stderr)
    print(json.dumps(stats))
    return 0


def cmd_search(args) -> int:
    from .config import load_config
    from .engine import Engine, Options, display_parent

    cfg = load_config()
    engine = Engine(cfg)
    opts = Options(rerank=args.rerank or cfg.rerank)
    for flag in ("semantic", "lexical", "content", "signals", "parse"):
        if getattr(args, f"no_{flag}"):
            setattr(opts, flag, False)
    res = engine.search(args.query, opts)
    p = res["parsed"]
    print(f"text={p.text!r} exts={sorted(p.exts) if p.exts else '-'} date={p.date_label or '-'}  {res['ms']:.1f} ms")
    pattern = engine.word_pattern(p.text)
    for i, h in enumerate(res["hits"][: args.n]):
        m = engine.catalog.files[h.id]
        print(f"{i + 1:2}. {m.name}  [{', '.join(engine.explain(p.text, h))}]  {display_parent(m)}")
        if args.debug:
            print(f"     score={h.score:.4f} lex={h.lex_rank} sem={h.sem_rank} {h.debug}")
            snip, _ = engine.snippet(p.text, h, pattern)
            if snip:
                print(f"     {snip[:160]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="folio", description="Local natural-language file search for macOS.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Run the local server and file watcher")
    s.add_argument("--no-watch", action="store_true", help="Don't watch folders for changes")
    s.add_argument("--no-index", action="store_true", help="Don't index at start")
    s.add_argument("--open", action="store_true", help="Open the page in the browser")

    sub.add_parser("index", help="Index new and changed files")
    sub.add_parser("reindex", help="Rebuild the whole index")

    s = sub.add_parser("search", help="Search from the terminal")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=10)
    s.add_argument("--debug", action="store_true")
    s.add_argument("--rerank", action="store_true")
    for flag in ("semantic", "lexical", "content", "signals", "parse"):
        s.add_argument(f"--no-{flag}", action="store_true")

    s = sub.add_parser("eval", help="Measure ranking quality on a set of queries")
    s.add_argument("--queries", help="JSONL file (default: queries.jsonl in the data folder)")
    s.add_argument("--variant", action="append", default=[], help="name=key:value,key:value (repeatable)")
    s.add_argument("--preset", choices=["phases", "weights", "models", "rerank"], help="A predefined set of variants")
    s.add_argument("--failures", action="store_true", help="List the queries that miss the top 3")
    s.add_argument("--markdown", action="store_true", help="Print the table as Markdown")

    s = sub.add_parser("sample", help="Pick files to write evaluation queries for")
    s.add_argument("-n", type=int, default=60)
    s.add_argument("--seed", type=int, default=7)

    s = sub.add_parser("export-log", help="Turn your logged searches and clicks into evaluation queries")
    s.add_argument("--out")

    sub.add_parser("doctor", help="Check permissions, models and index")
    sub.add_parser("models", help="Download the models (the only network access)")
    sub.add_parser("status", help="Print index statistics")

    s = sub.add_parser("reset", help="Delete the index (keeps models and configuration)")
    s.add_argument("--yes", action="store_true", help="Don't ask for confirmation")
    s = sub.add_parser("uninstall", help="Delete everything folio created on this Mac")
    s.add_argument("--yes", action="store_true", help="Don't ask for confirmation")

    s = sub.add_parser("agent", help="Start folio at login (launchd)")
    s.add_argument("action", choices=["install", "uninstall", "status"])

    args = ap.parse_args(argv)

    if args.cmd == "index":
        return cmd_index(args)
    if args.cmd == "reindex":
        return cmd_index(args, full=True)
    if args.cmd == "search":
        return cmd_search(args)
    if args.cmd == "serve":
        from .server import serve

        return serve(watch=not args.no_watch, index_at_start=not args.no_index, open_browser=args.open)
    if args.cmd == "eval":
        from .evaluate import run_eval

        return run_eval(args)
    if args.cmd == "sample":
        from .evaluate import sample

        return sample(args)
    if args.cmd == "export-log":
        from .evaluate import export_log

        return export_log(args)
    if args.cmd == "doctor":
        from .doctor import doctor

        return doctor()
    if args.cmd == "models":
        from .config import load_config
        from .models import EMBEDDERS, RERANKERS, ensure_model

        cfg = load_config()
        ensure_model(EMBEDDERS[cfg.embedding_model])
        ensure_model(RERANKERS["mmarco-minilm"])
        print("Models are in place.")
        return 0
    if args.cmd == "status":
        from .doctor import status

        return status()
    if args.cmd in ("reset", "uninstall"):
        from . import cleanup

        return getattr(cleanup, args.cmd)(yes=args.yes)
    if args.cmd == "agent":
        from . import launchd

        return launchd.main(args.action)
    return 1


if __name__ == "__main__":
    sys.exit(main())
