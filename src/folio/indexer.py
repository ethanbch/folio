"""Indexing pipeline: walk → metadata → names → content → vectors. Incremental on mtime and size."""

from __future__ import annotations

import ctypes
import os
import threading
import time
from dataclasses import dataclass

import numpy as np

from . import db, macos, models
from .chunking import chunks, context_label, passage
from .config import Config
from .crawl import PACKAGE_EXTS, Entry, Excluder, walk
from .engine import ROOT_ALIASES, Engine, split_root
from .extract import ExtractPool
from .kinds import EXTRACTABLE, kind_of
from .models import Embedder
from .textnorm import nfc

BATCH = 48


@dataclass
class Progress:
    phase: str = "idle"  # idle, model, scanning, names, content, paused, done, stopped, error
    done: int = 0  # files processed in the content phase
    total: int = 0
    work_done: float = 0.0  # weighted: a large local PDF counts more than an iCloud placeholder
    work_total: float = 0.0
    work_session: float = 0.0  # done since this run started, for the time estimate
    total_before: int = 0  # files already indexed when a run resumes
    found: int = 0  # files found while walking
    current: str = ""  # file being read
    content_ok: int = 0  # files whose text was read
    name_only: int = 0  # files indexed by name and folder only
    model_label: str = ""
    model_done: int = 0  # bytes
    model_total: int = 0
    model_index: int = 0  # 1-based rank of the file being downloaded
    model_count: int = 0
    started: float = 0.0
    content_started: float = 0.0
    finished: float = 0.0
    message: str = ""
    last_run_s: float | None = None
    errors: int = 0
    battery: int | None = None
    first_run: bool = False

    def eta_s(self) -> float | None:
        """Seconds left in the content phase, from the weighted rate so far."""
        if self.phase not in ("content", "paused") or not self.work_session or not self.content_started:
            return None
        elapsed = time.time() - self.content_started
        if elapsed < 5:
            return None
        return max(0.0, (self.work_total - self.work_done) * elapsed / self.work_session)

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["eta_s"] = self.eta_s()
        d["pct"] = round(100 * self.work_done / self.work_total, 1) if self.work_total else 0.0
        return d


TEXT_LIKE = {"txt", "md", "markdown", "csv", "tsv", "json", "html", "htm", "xml", "tex", "rst", "py", "js", "ts", "ipynb"}


def work_weight(r, max_bytes: float, max_chunks: int) -> float:
    """Estimated cost of a file, in units of "one small file". Measured on an M3: a 16-chunk PDF
    takes ≈ 1 s, a name-only file ≈ 6 ms."""
    if r["dataless"] or r["ext"] not in EXTRACTABLE or r["size"] > max_bytes:
        return 0.03
    per_chunk = 1100 if r["ext"] in TEXT_LIKE else 25_000  # bytes of file per chunk of text, roughly
    return 1.0 + min(max_chunks, r["size"] / per_chunk)


def _ext(name: str, is_package: bool = False) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name.strip(".") else ""


QOS_UTILITY = 0x11  # low priority, may use performance cores: a run the user asked for
QOS_BACKGROUND = 0x09  # efficiency cores, throttled I/O: watcher updates


def set_thread_qos(qos: int) -> None:
    try:
        libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        libc.pthread_set_qos_class_self_np(qos, 0)
    except (OSError, AttributeError):
        pass


class Indexer:
    def __init__(self, engine: Engine, cfg: Config):
        self.engine = engine
        self.cfg = cfg
        self.progress = Progress()
        self.lock = threading.Lock()  # one indexing pass at a time
        self.stop = threading.Event()
        self.battery_override = threading.Event()  # the user chose to continue on battery, for this run
        self.wake = threading.Event()  # interrupts the battery wait

    # ── Walk ────────────────────────────────────────────────────────────────

    def _row_values(self, e: Entry) -> dict:
        name = nfc(os.path.basename(e.path))
        ext = _ext(name)
        st = e.stat
        return {
            "path": nfc(e.path),
            "name": name,
            "ext": ext,
            "kind": kind_of(ext),
            "size": 0 if e.is_package else st.st_size,
            "mtime": st.st_mtime,
            "ctime": getattr(st, "st_birthtime", st.st_ctime),
            "last_used": macos.last_used(e.path),
            "dataless": int(macos.is_dataless(st)),
        }

    def scan(self) -> tuple[int, int, int]:
        """Walk the roots and update metadata. Returns (new, changed, deleted)."""
        conn = db.connect()
        gen = int(db.get_meta("gen", "0")) + 1
        known = {r["path"]: r for r in conn.execute("SELECT id, path, size, mtime, dataless, status FROM files")}
        new = changed = 0
        self.progress.phase, self.progress.message = "scanning", "Walking folders"
        self.progress.found = 0
        batch_new, batch_changed, batch_seen = [], [], []
        for e in walk(self.cfg):
            self.progress.found += 1
            v = self._row_values(e)
            v["seen"] = gen
            old = known.get(v["path"])
            if old is None:
                batch_new.append(v)
                new += 1
            elif old["mtime"] != v["mtime"] or old["size"] != v["size"] or (old["dataless"] and not v["dataless"]):
                v["id"] = old["id"]
                batch_changed.append(v)
                changed += 1
            else:
                batch_seen.append((gen, v["last_used"], v["dataless"], old["id"]))
        conn.executemany(
            "INSERT INTO files(path, name, ext, kind, size, mtime, ctime, last_used, dataless, seen) "
            "VALUES (:path, :name, :ext, :kind, :size, :mtime, :ctime, :last_used, :dataless, :seen)",
            batch_new,
        )
        conn.executemany(
            "UPDATE files SET name=:name, ext=:ext, kind=:kind, size=:size, mtime=:mtime, ctime=:ctime, last_used=:last_used, "
            "dataless=:dataless, seen=:seen, status='pending', error=NULL, lexical_mtime=NULL, embedded_mtime=NULL WHERE id=:id",
            batch_changed,
        )
        conn.executemany("UPDATE files SET seen=?, last_used=?, dataless=? WHERE id=?", batch_seen)
        # Files not seen: deleted, unless their root is unreachable (unmounted volume, iCloud off).
        live_roots = [str(r) for r in self.cfg.root_paths if r.is_dir()]
        gone = [
            r["id"]
            for r in conn.execute("SELECT id, path FROM files WHERE seen != ?", (gen,))
            if any(r["path"].startswith(root + "/") for root in live_roots)
            or not any(r["path"].startswith(str(x) + "/") for x in self.cfg.root_paths)
        ]
        self._delete(gone)
        conn.commit()
        db.set_meta("gen", str(gen))
        self.engine.catalog.reload()
        return new, changed, len(gone)

    def _delete(self, ids: list[int]) -> None:
        if not ids:
            return
        conn = db.connect()
        for fid in ids:
            self.engine.lexical.delete(fid)
            rows = [r[0] for r in conn.execute("SELECT row FROM chunks WHERE file_id=?", (fid,))]
            self.engine.vectors.kill(rows)
            conn.execute("DELETE FROM chunks WHERE file_id=?", (fid,))
            conn.execute("DELETE FROM files WHERE id=?", (fid,))
        conn.commit()

    # ── Single paths (watcher) ──────────────────────────────────────────────

    def update_paths(self, paths: set[str]) -> None:
        """Re-check paths reported by the file watcher, then index what changed."""
        ex = Excluder(self.cfg)
        conn = db.connect()
        roots = self.cfg.root_paths
        changed_ids: list[int] = []
        for path in paths:
            path = nfc(path)
            try:
                st = os.stat(path, follow_symlinks=False)
            except OSError:
                st = None
            # A deleted or renamed folder: drop everything under it.
            if st is None:
                ids = [
                    r[0] for r in conn.execute("SELECT id FROM files WHERE path = ? OR path LIKE ? ESCAPE '\\'", (path, _like_prefix(path)))
                ]
                self._delete(ids)
                changed_ids += ids
                continue
            import stat as stmod

            is_dir = stmod.S_ISDIR(st.st_mode)
            is_package = is_dir and _ext(os.path.basename(path)) in PACKAGE_EXTS
            if is_dir and not is_package:
                # New or moved folder: walk it.
                if not ex.excluded(os.path.join(path, "x"), roots):
                    sub = Config(**{**self.cfg.__dict__, "roots": [path], "icloud": False})
                    for e in walk(sub):
                        changed_ids += self._upsert_entry(e)
                continue
            if ex.excluded(path, roots):
                continue
            changed_ids += self._upsert_entry(Entry(path, st, is_package))
        conn.commit()
        self.engine.catalog.update(changed_ids)
        if changed_ids:
            self.process(bulk=False)

    def _upsert_entry(self, e: Entry) -> list[int]:
        conn = db.connect()
        v = self._row_values(e)
        row = conn.execute("SELECT id, mtime, size, dataless FROM files WHERE path=?", (v["path"],)).fetchone()
        if row and row["mtime"] == v["mtime"] and row["size"] == v["size"] and not (row["dataless"] and not v["dataless"]):
            return []
        v["seen"] = int(db.get_meta("gen", "0"))
        if row:
            v["id"] = row["id"]
            conn.execute(
                "UPDATE files SET name=:name, ext=:ext, kind=:kind, size=:size, mtime=:mtime, ctime=:ctime, last_used=:last_used, "
                "dataless=:dataless, seen=:seen, status='pending', error=NULL, lexical_mtime=NULL, embedded_mtime=NULL WHERE id=:id",
                v,
            )
            return [row["id"]]
        cur = conn.execute(
            "INSERT INTO files(path, name, ext, kind, size, mtime, ctime, last_used, dataless, seen) "
            "VALUES (:path, :name, :ext, :kind, :size, :mtime, :ctime, :last_used, :dataless, :seen)",
            v,
        )
        return [cur.lastrowid]

    # ── Content and vectors ─────────────────────────────────────────────────

    def _wait_for_power(self) -> None:
        while not self.stop.is_set() and not self.battery_override.is_set():
            on_batt, pct = macos.battery()
            if not on_batt or pct is None or pct >= self.cfg.min_battery_percent:
                break
            self.progress.phase = "paused"
            self.progress.message = f"Paused: battery at {pct} %"
            self.progress.battery = pct
            self.wake.wait(3)  # plugging in resumes within 3 s; pmset costs a few ms
            self.wake.clear()
        if self.progress.phase == "paused":
            self.progress.phase = "content"
            self.progress.battery = None

    def index_names(self) -> int:
        """Make every new file findable by name and folder before content extraction starts."""
        conn = db.connect()
        rows = conn.execute("SELECT id, path, name, ext FROM files WHERE lexical_mtime IS NULL").fetchall()
        self.progress.phase, self.progress.message = "names", "Indexing names"
        for r in rows:
            root, rel = split_root(r["path"], self.engine.roots)
            self.engine.lexical.upsert(r["id"], r["name"], f"{ROOT_ALIASES.get(root, root)}/{rel}", r["ext"], "")
        if rows:
            self.engine.lexical.commit()
        return len(rows)

    def process(self, bulk: bool = True) -> int:
        """Extract, index and embed every file whose index entry is out of date."""
        conn = db.connect()
        rows = conn.execute(
            "SELECT id, path, name, ext, size, mtime, dataless, status FROM files "
            "WHERE status='pending' OR lexical_mtime IS NULL OR lexical_mtime != mtime OR embedded_mtime IS NULL OR embedded_mtime != mtime "
            "ORDER BY dataless, mtime DESC"
        ).fetchall()
        if not rows:
            return 0
        embedder = self._embedder(bulk and len(rows) > 50)
        pool = ExtractPool(workers=3 if bulk else 1, timeout=self.cfg.extract_timeout_s)
        max_bytes = self.cfg.max_content_mb * 1_000_000
        weights = {r["id"]: work_weight(r, max_bytes, self.cfg.max_chunks_per_file) for r in rows}
        p = self.progress
        p.phase, p.message = "content", "Extracting content and computing vectors"
        p.total, p.done = len(rows), 0
        p.work_total, p.work_done, p.work_session = sum(weights.values()), 0.0, 0.0
        if bulk:
            # A resumed run counts the files done before the interruption, so the bar doesn't restart at 0 %.
            todo = set(weights)
            done_rows = [r for r in conn.execute("SELECT id, ext, size, dataless, status FROM files") if r["id"] not in todo]
            p.done = p.total_before = len(done_rows)
            p.total += len(done_rows)
            p.content_ok = sum(r["status"] == "ok" for r in done_rows)
            p.name_only = len(done_rows) - p.content_ok
            before = sum(work_weight(r, max_bytes, self.cfg.max_chunks_per_file) for r in done_rows)
            p.work_total += before
            p.work_done = before
        p.content_started = time.time()
        last_commit = time.monotonic()
        writes: list[tuple] = []
        last_power_check = time.monotonic()
        try:
            for s in range(0, len(rows), BATCH):
                if self.stop.is_set():
                    break
                self._wait_for_power()
                batch = rows[s : s + BATCH]
                status: dict[int, tuple[str, str | None]] = {}
                texts: dict[int, str] = {}
                tasks = []
                for r in batch:
                    if r["dataless"]:
                        status[r["id"]] = ("dataless", None)
                    elif r["ext"] not in EXTRACTABLE or os.path.isdir(r["path"]):
                        status[r["id"]] = ("skipped", None)
                    elif r["size"] > max_bytes:
                        status[r["id"]] = ("too_big", None)
                    else:
                        tasks.append((r["id"], r["path"], r["ext"], self.cfg.max_content_chars))
                for res in pool.map(tasks):
                    status[res.key] = (res.status, res.error)
                    texts[res.key] = res.text
                    if res.status in ("error", "timeout"):
                        self.progress.errors += 1
                for r in batch:
                    if self.stop.is_set():
                        break
                    if time.monotonic() - last_power_check > 2:  # unplugging pauses within ≈ 2 s
                        self._wait_for_power()
                        last_power_check = time.monotonic()
                    p.current = r["name"]
                    writes.append(self._index_one(r, texts.get(r["id"], ""), status[r["id"]], embedder))
                    p.done += 1
                    p.work_done += weights[r["id"]]
                    p.work_session += weights[r["id"]]
                    if status[r["id"]][0] == "ok":
                        p.content_ok += 1
                    else:
                        p.name_only += 1
                if time.monotonic() - last_commit > 10 or s + BATCH >= len(rows):
                    self._flush(writes)
                    writes = []
                    last_commit = time.monotonic()
        finally:
            pool.close()
            self._flush(writes)
            p.current = ""
        return len(rows)

    def _flush(self, writes: list[tuple]) -> None:
        """tantivy first, then SQLite in one short transaction: a crash in between only re-indexes
        these files, and the write lock is held for milliseconds, not for the whole batch."""
        self.engine.lexical.commit()
        if not writes:
            return
        conn = db.connect()
        with conn:
            for fid, chunk_rows, update in writes:
                conn.execute("DELETE FROM chunks WHERE file_id=?", (fid,))
                conn.executemany("INSERT INTO chunks(row, file_id, start, end) VALUES (?, ?, ?, ?)", chunk_rows)
                conn.execute(
                    "UPDATE files SET status=?, error=?, content_chars=?, lexical_mtime=mtime, embedded_mtime=mtime WHERE id=?", update
                )
        self.engine.catalog.update([w[0] for w in writes])

    def _embedder(self, bulk: bool) -> Embedder:
        """One model copy (≈ 350 MB resident), shared with queries: a second copy would double memory."""
        if self.engine.embedder is None:
            self.engine.load_embedder()
        return self.engine.embedder

    def _index_one(self, r, text: str, st: tuple[str, str | None], embedder: Embedder) -> tuple:
        """Index one file in tantivy and the vector file. Returns its SQLite writes, applied by _flush."""
        conn = db.connect()
        eng = self.engine
        root, rel = split_root(r["path"], eng.roots)
        eng.lexical.upsert(r["id"], r["name"], f"{ROOT_ALIASES.get(root, root)}/{rel}", r["ext"], text)
        # Vectors: one for the name and folders, then one per content chunk.
        old = [x[0] for x in conn.execute("SELECT row FROM chunks WHERE file_id=?", (r["id"],))]
        eng.vectors.kill(old)
        label = context_label(r["name"], f"{root}/{rel}" if rel else root)
        spans = chunks(text, self.cfg.max_chunks_per_file) if text else []
        passages = [label] + [passage(r["name"], rel, text[a:b]) for a, b in spans]
        lock = eng.embed_lock
        parts = []
        for i in range(0, len(passages), 4):
            while eng.queries_waiting:  # a query is waiting for the model: let it go first
                time.sleep(0.002)
            with lock:  # small batches: a query waits ≈ 50 ms at most
                parts.append(embedder.embed_passages(passages[i : i + 4]))
        vecs = np.concatenate(parts)
        new_rows = eng.vectors.append(vecs, r["id"])
        chunk_rows = [(new_rows[0], r["id"], 0, 0)] + [(row, r["id"], a, b) for row, (a, b) in zip(new_rows[1:], spans)]
        return r["id"], chunk_rows, (st[0], st[1], len(text), r["id"])

    # ── Full run ────────────────────────────────────────────────────────────

    def run(self, full: bool = False, qos: int = QOS_UTILITY) -> dict:
        with self.lock:
            set_thread_qos(qos)
            self.progress = Progress(started=time.time(), first_run=not db.get_meta("last_index"))
            self.battery_override.clear()
            db.set_meta("index_requested", "1")  # an interrupted run resumes at the next start
            t0 = time.monotonic()
            if full:
                self._reset()
            if self.engine.embedder is None and not self.engine.model_ready():
                self.progress.phase, self.progress.message = "model", "Downloading the models"
                self.progress.model_count = models.missing_files(self.cfg.embedding_model, self.cfg.rerank)
                models.DOWNLOAD_HOOK = self._download_progress
                try:
                    self.engine.load_embedder()
                    if self.cfg.rerank:
                        self.engine.load_reranker()
                finally:
                    models.DOWNLOAD_HOOK = None
            new, changed, deleted = self.scan()
            t_scan = time.monotonic() - t0
            self.index_names()
            t_names = time.monotonic() - t0
            n = 0 if self.stop.is_set() else self.process(bulk=True)
            if self.stop.is_set():  # stopped by the user, or index deleted: no "done", no last_index
                self.progress.phase = "stopped"
                self.progress.current = ""
                return {"stopped": True}
            self._maybe_compact()
            self.progress.phase = "done"
            self.progress.finished = time.time()
            self.progress.last_run_s = time.monotonic() - t0
            self.progress.message = "Index up to date"
            stats = {
                "new": new,
                "changed": changed,
                "deleted": deleted,
                "processed": n,
                "scan_s": round(t_scan, 1),
                "names_s": round(t_names, 1),
                "total_s": round(self.progress.last_run_s, 1),
            }
            db.set_meta("last_index", f"{time.time()}")
            return stats

    def continue_on_battery(self) -> bool:
        """Resume a run paused for low battery. Applies to this run only."""
        if not self.lock.locked():
            return False
        self.battery_override.set()
        self.wake.set()
        return True

    def cancel(self) -> bool:
        """Stop the running pass. What is indexed stays; the next run continues from there.
        A stopped first run does not resume by itself at the next start."""
        if not self.lock.locked():
            return False
        self.stop.set()
        self.wake.set()
        with self.lock:
            self.stop.clear()
        if not db.get_meta("last_index"):
            db.connect().execute("DELETE FROM meta WHERE key = 'index_requested'")
            db.connect().commit()
        return True

    def delete_index(self) -> None:
        """Stop any run, then delete the index and the search history. Models and configuration stay."""
        self.stop.set()
        self.wake.set()
        with self.lock:
            self.stop.clear()
            conn = db.connect()
            with conn:
                for table in ("chunks", "files", "searches", "clicks"):
                    conn.execute(f"DELETE FROM {table}")
                conn.execute("DELETE FROM meta WHERE key IN ('last_index', 'gen', 'index_requested')")
            conn.execute("VACUUM")
            self.engine.lexical.clear()
            self.engine.vectors.compact({})
            self.engine.load_owners()
            self.engine.catalog.reload()
            self.engine.frecency.invalidate()
            self.progress = Progress()

    def _download_progress(self, label: str, done: int, total: int) -> None:
        p = self.progress
        if label != p.model_label:
            p.model_index += 1
        p.model_label, p.model_done, p.model_total = label, done, total

    def _reset(self) -> None:
        conn = db.connect()
        conn.execute("DELETE FROM chunks")
        conn.execute("UPDATE files SET status='pending', lexical_mtime=NULL, embedded_mtime=NULL")
        conn.commit()
        self.engine.lexical.clear()
        self.engine.vectors.compact({})

    def _maybe_compact(self) -> None:
        if self.engine.vectors.dead_ratio() < 0.3:
            return
        conn = db.connect()
        by_file: dict[int, list[int]] = {}
        for row, fid in conn.execute("SELECT row, file_id FROM chunks ORDER BY row"):
            by_file.setdefault(fid, []).append(row)
        mapping = self.engine.vectors.compact(by_file)
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS remap(old INTEGER PRIMARY KEY, new INTEGER)")
        conn.execute("DELETE FROM remap")
        conn.executemany("INSERT INTO remap VALUES (?, ?)", mapping.items())
        conn.execute("UPDATE chunks SET row = -1 - (SELECT new FROM remap WHERE old = chunks.row)")
        conn.execute("UPDATE chunks SET row = -1 - row")
        conn.commit()
        self.engine.load_owners()


def _like_prefix(path: str) -> str:
    esc = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return esc.rstrip("/") + "/%"
