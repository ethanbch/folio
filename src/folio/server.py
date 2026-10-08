"""Local web server: search API, actions on files, status, and the page itself.

Listens on 127.0.0.1 only. Routes that act on the machine (open, reveal, Quick Look,
index) accept POST only, and require:
- a Host header naming 127.0.0.1 or localhost on our port (blocks DNS rebinding);
- an Origin header, when present, from the same host (blocks cross-site requests);
- the per-run random token, which is injected in the page and never served elsewhere.
"""

from __future__ import annotations

import hmac
import os
import queue
import secrets
import sqlite3
import sys
import threading
import time
import webbrowser
from importlib import resources

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from . import __version__, db, macos
from .config import HOME, ICLOUD_DIR, Config, config_path, data_path, load_config
from .engine import Engine, Options, display_parent
from .kinds import KINDS

STATE: dict = {}


def _allowed_hosts(port: int) -> set[str]:
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


class GuardMiddleware:
    """Rejects requests whose Host or Origin is not this server."""

    def __init__(self, app, port: int):
        self.app = app
        self.hosts = _allowed_hosts(port)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        host = headers.get("host", "")
        origin = headers.get("origin")
        ok = host in self.hosts and (origin is None or origin.split("://", 1)[-1] in self.hosts)
        if not ok:
            resp = Response("Forbidden", status_code=403)
            return await resp(scope, receive, send)
        return await self.app(scope, receive, send)


def _check_token(request: Request) -> bool:
    return hmac.compare_digest(request.headers.get("x-folio-token", ""), STATE["token"])


def _deny() -> JSONResponse:
    return JSONResponse({"error": "Request refused: missing or invalid token. Reload the page."}, status_code=403)


# ── Page and assets ─────────────────────────────────────────────────────────

_ASSET_TYPES = {
    ".css": "text/css",
    ".js": "text/javascript",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".png": "image/png",
    ".webmanifest": "application/manifest+json",
}


def _web(name: str) -> bytes:
    return resources.files("folio").joinpath("web", name).read_bytes()


async def page(request: Request) -> Response:
    html = _web("index.html").decode().replace("__FOLIO_TOKEN__", STATE["token"]).replace("__FOLIO_VERSION__", __version__)
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        },
    )


async def asset(request: Request) -> Response:
    name = request.path_params["name"]
    if "/" in name or ".." in name:
        return Response(status_code=404)
    ext = os.path.splitext(name)[1]
    try:
        data = _web(name)
    except (FileNotFoundError, IsADirectoryError):
        return Response(status_code=404)
    return Response(data, media_type=_ASSET_TYPES.get(ext, "application/octet-stream"), headers={"Cache-Control": "no-cache"})


# ── API ─────────────────────────────────────────────────────────────────────


def _result(engine: Engine, text: str, h, pattern) -> dict:
    m = engine.catalog.files[h.id]
    snippet, ranges = engine.snippet(text, h, pattern)
    return {
        "id": m.id,
        "name": m.name,
        "path": m.path,
        "parent": display_parent(m),
        "ext": m.ext,
        "kind": m.kind,
        "size": m.size,
        "mtime": m.mtime,
        "last_used": m.last_used,
        "icloud": m.dataless,
        "snippet": snippet,
        "highlights": ranges,
        "name_highlights": [(x.start(), x.end()) for x in pattern.finditer(m.name)] if pattern else [],
        "reasons": engine.explain(text, h),
        "score": round(h.score, 5),
        "debug": h.debug,
    }


def _search(q: str, disabled: set[str], rerank: bool, kinds: set[str] | None, days: int | None, limit: int) -> dict:
    engine: Engine = STATE["engine"]
    exts = set().union(*(KINDS.get(k, set()) for k in kinds)) if kinds else None
    since = time.time() - days * 86400 if days else None
    res = engine.search(q, Options(rerank=rerank, semantic=engine.embedder is not None, limit=limit), disabled, exts, since)
    parsed = res["parsed"]
    pattern = engine.word_pattern(parsed.text)
    return {
        "query": q,
        "text": parsed.text,
        "chips": parsed.chips,
        "relaxed": res["relaxed"],
        "ms": round(res["ms"], 1),
        "semantic": engine.embedder is not None,
        "results": [_result(engine, parsed.text, h, pattern) for h in res["hits"]],
    }


def _params(request: Request):
    q = request.query_params.get("q", "")[:300]
    disabled = set(filter(None, request.query_params.get("off", "").split(",")))
    kinds = set(filter(None, request.query_params.get("kind", "").split(","))) or None
    days = int(request.query_params["days"]) if request.query_params.get("days", "").isdigit() else None
    return q, disabled, kinds, days


async def api_search(request: Request) -> Response:
    if not _check_token(request):
        return _deny()
    q, disabled, kinds, days = _params(request)
    rerank = request.query_params.get("rerank") == "1" or (request.query_params.get("rerank") is None and STATE["cfg"].rerank)
    rerank = rerank and STATE["engine"].reranker_ready
    t0 = time.perf_counter()
    out = await _run(_search, q, disabled, rerank, kinds, days, 30)
    if request.query_params.get("rerank") != "1":  # the second phase repeats the query: log it once
        _log_search(q, len(out["results"]), (time.perf_counter() - t0) * 1000)
    return JSONResponse(out)


_log_queue: queue.SimpleQueue = queue.SimpleQueue()


def _log_writer() -> None:
    """Writes the search and click log from its own thread: a request never waits on SQLite."""
    while True:
        sql, args = _log_queue.get()
        try:
            conn = db.connect()
            conn.execute(sql, args)
            conn.commit()
        except sqlite3.Error as e:
            print(f"log: {e}", file=sys.stderr)


def _log(sql: str, args: tuple) -> None:
    _log_queue.put((sql, args))


def _log_search(q: str, n: int, ms: float) -> None:
    if q.strip():
        _log("INSERT INTO searches(ts, query, results, ms) VALUES (?, ?, ?, ?)", (time.time(), q, n, ms))


async def _run(fn, *args):
    import anyio

    return await anyio.to_thread.run_sync(lambda: fn(*args))


async def api_action(request: Request) -> Response:
    if not _check_token(request):
        return _deny()
    body = await request.json()
    action = request.path_params["action"]
    engine: Engine = STATE["engine"]
    try:
        fid = int(body.get("id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Missing file id."}, status_code=400)
    m = engine.catalog.files.get(fid)
    if m is None:
        return JSONResponse({"error": "This file is not in the index."}, status_code=404)
    if not os.path.lexists(m.path):
        return JSONResponse({"error": f"The file no longer exists: {m.path}"}, status_code=410)
    if action == "open":
        macos.open_file(m.path)
    elif action == "reveal":
        macos.reveal(m.path)
    elif action == "preview":
        macos.quicklook(m.path)
    else:
        return JSONResponse({"error": "Unknown action."}, status_code=404)
    if action in ("open", "reveal") or body.get("log"):
        _log(
            "INSERT INTO clicks(ts, query, file_id, path, rank, action) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), str(body.get("query", ""))[:300], fid, m.path, int(body.get("rank", -1)), action),
        )
        engine.frecency.invalidate()
    return JSONResponse({"ok": True})


async def api_log_copy(request: Request) -> Response:
    """Copying a path counts as a click for ranking."""
    if not _check_token(request):
        return _deny()
    body = await request.json()
    engine: Engine = STATE["engine"]
    m = engine.catalog.files.get(int(body.get("id", -1)))
    if m:
        _log(
            "INSERT INTO clicks(ts, query, file_id, path, rank, action) VALUES (?, ?, ?, ?, ?, 'copy')",
            (time.time(), str(body.get("query", ""))[:300], m.id, m.path, int(body.get("rank", -1))),
        )
        engine.frecency.invalidate()
    return JSONResponse({"ok": True})


async def api_index(request: Request) -> Response:
    if not _check_token(request):
        return _deny()
    try:
        body = await request.json()
    except ValueError:
        body = {}
    started = start_indexing(full=bool(body.get("full")))
    return JSONResponse({"started": started}, status_code=202 if started else 409)


async def api_continue(request: Request) -> Response:
    """Continue an indexing paused for low battery (this run only)."""
    if not _check_token(request):
        return _deny()
    return JSONResponse({"continued": STATE["indexer"].continue_on_battery()})


async def api_cancel(request: Request) -> Response:
    """Stops indexing. What is already indexed stays searchable."""
    if not _check_token(request):
        return _deny()
    return JSONResponse({"stopped": await _run(STATE["indexer"].cancel)})


async def api_reset(request: Request) -> Response:
    """Deletes the index and the search history. Models and configuration stay."""
    if not _check_token(request):
        return _deny()
    await _run(STATE["indexer"].delete_index)
    return JSONResponse({"ok": True})


def start_indexing(full: bool = False) -> bool:
    idx = STATE["indexer"]
    if idx.lock.locked():
        return False

    def run():
        try:
            idx.run(full=full)
        except Exception as e:  # noqa: BLE001 - shown on the status page
            idx.progress.phase = "error"
            idx.progress.message = f"Indexing failed: {type(e).__name__}: {e}"
            print(idx.progress.message, file=sys.stderr)

    threading.Thread(target=run, name="indexer", daemon=True).start()
    return True


async def api_status(request: Request) -> Response:
    if not _check_token(request):
        return _deny()
    conn = db.connect()
    counts = dict(conn.execute("SELECT status, COUNT(*) FROM files GROUP BY status").fetchall())
    index_bytes = sum(f.stat().st_size for d in ("tantivy", "vectors") for f in data_path(d).rglob("*") if f.is_file())
    index_bytes += sum(data_path(n).stat().st_size for n in ("folio.db", "folio.db-wal") if data_path(n).exists())
    kinds = dict(conn.execute("SELECT kind, COUNT(*) FROM files GROUP BY kind ORDER BY 2 DESC").fetchall())
    errors = [
        dict(r)
        for r in conn.execute("SELECT path, status, error FROM files WHERE status IN ('error', 'timeout') ORDER BY mtime DESC LIMIT 50")
    ]
    engine: Engine = STATE["engine"]
    idx = STATE["indexer"]
    last = db.get_meta("last_index")
    return JSONResponse(
        {
            "version": __version__,
            "files": sum(counts.values()),
            "by_status": counts,
            "by_kind": kinds,
            "chunks": int((engine.vectors.owner >= 0).sum()),
            "errors": errors,
            "progress": idx.progress.as_dict(),
            "indexing": idx.lock.locked(),
            "last_index": float(last) if last else None,
            "roots": [("iCloud Drive" if r == ICLOUD_DIR else str(r).replace(str(HOME), "~", 1)) for r in engine.roots],
            "full_disk_access": macos.has_full_disk_access(),
            "rss_mb": _rss_mb(),
            "config_path": str(config_path()).replace(str(HOME), "~", 1),
            "model": engine.cfg.embedding_model,
            "rerank": engine.cfg.rerank and engine.reranker_ready,
            "watching": STATE.get("watching", False),
            "min_battery": engine.cfg.min_battery_percent,
            "models_ready": engine.model_ready(),
            "index_bytes": index_bytes,
        }
    )


def _rss_mb() -> float:
    import resource

    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 1)


# Seconds per unit of indexing work (indexer.work_weight), measured on an M3 MacBook Air: 4 408 files,
# 9 506 units, 364 s. Shown as an estimate (≈) before the first run.
SECONDS_PER_UNIT = 0.038
_preview_cache: dict = {}


def _preview() -> dict:
    """What a first run would index: a walk of the folders, no file opened (≈ 0.2 s for 4 400 files)."""
    from .crawl import walk
    from .engine import split_root
    from .indexer import work_weight
    from .kinds import EXTRACTABLE

    cached = _preview_cache.get("value")
    if cached and time.time() - _preview_cache["at"] < 30:
        return cached
    cfg: Config = STATE["cfg"]
    engine: Engine = STATE["engine"]
    by_root: dict[str, int] = {}
    total = readable = cloud = 0
    work = 0.0
    max_bytes = cfg.max_content_mb * 1_000_000
    for e in walk(cfg):
        name = os.path.basename(e.path)
        ext = name.rsplit(".", 1)[-1].lower() if "." in name.strip(".") else ""
        dataless = macos.is_dataless(e.stat)
        row = {"dataless": dataless, "ext": ext, "size": 0 if e.is_package else e.stat.st_size}
        work += work_weight(row, max_bytes, cfg.max_chunks_per_file)
        root, _ = split_root(e.path, engine.roots)
        by_root[root] = by_root.get(root, 0) + 1
        total += 1
        cloud += dataless
        readable += (not dataless) and ext in EXTRACTABLE and row["size"] <= max_bytes
    value = {
        "total": total,
        "by_root": sorted(({"label": k, "count": v} for k, v in by_root.items()), key=lambda r: -r["count"]),
        "readable": readable,
        "cloud": cloud,
        "estimate_s": round(work * SECONDS_PER_UNIT),
    }
    _preview_cache.update(value=value, at=time.time())
    return value


async def api_preview(request: Request) -> Response:
    if not _check_token(request):
        return _deny()
    return JSONResponse(await _run(_preview))


async def api_ping(request: Request) -> Response:
    return JSONResponse({"ok": True, "version": __version__})


def build_app(port: int) -> Starlette:
    routes = [
        Route("/", page),
        Route("/assets/{name}", asset),
        Route("/api/ping", api_ping),
        Route("/api/search", api_search),
        Route("/api/status", api_status),
        Route("/api/preview", api_preview),
        Route("/api/index", api_index, methods=["POST"]),
        Route("/api/index/cancel", api_cancel, methods=["POST"]),
        Route("/api/index/continue", api_continue, methods=["POST"]),
        Route("/api/reset", api_reset, methods=["POST"]),
        Route("/api/copied", api_log_copy, methods=["POST"]),
        Route("/api/{action}", api_action, methods=["POST"]),
    ]
    return Starlette(routes=routes, middleware=[Middleware(GuardMiddleware, port=port)])


def serve(watch: bool = True, index_at_start: bool = True, open_browser: bool = False) -> int:
    import faulthandler
    import signal

    import uvicorn

    from .indexer import Indexer

    faulthandler.register(signal.SIGUSR1)  # `kill -USR1 <pid>` prints every thread's stack to the log
    cfg = load_config()
    STATE["cfg"] = cfg
    STATE["token"] = secrets.token_urlsafe(32)
    token_file = data_path("server.token")
    token_file.write_text(STATE["token"])
    os.chmod(token_file, 0o600)
    data_path("server.pid").write_text(str(os.getpid()))
    engine = Engine(cfg, load_models=False)
    STATE["engine"] = engine
    threading.Thread(target=_log_writer, name="log", daemon=True).start()
    if engine.model_ready():
        # Answer at once with names and folders; semantic search joins when the model is loaded (≈ 1-3 s).
        def load():
            engine.load_embedder(allow_download=False)
            if cfg.rerank:
                engine.load_reranker(allow_download=False)

        threading.Thread(target=load, daemon=True).start()
    STATE["indexer"] = Indexer(engine, cfg)
    # Index at start once the user asked for it (button or `folio index`): this catches up on changes
    # made while folio was off, and resumes a first run that was interrupted. Before that, wait for the button.
    if index_at_start and (db.get_meta("last_index") or db.get_meta("index_requested")):
        start_indexing()
    if watch:
        from .watcher import start_watcher

        STATE["watching"] = start_watcher(cfg, STATE["indexer"])
    url = f"http://127.0.0.1:{cfg.port}/"
    print(f"folio {__version__} at {url}", file=sys.stderr)
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        build_app(cfg.port),
        host="127.0.0.1",
        port=cfg.port,
        log_level="info" if os.environ.get("FOLIO_ACCESS_LOG") else "warning",
        access_log=bool(os.environ.get("FOLIO_ACCESS_LOG")),
    )
    return 0
