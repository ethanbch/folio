"""File watcher (FSEvents through watchdog), with debounce."""

from __future__ import annotations

import sys
import threading
import time

from . import db
from .config import Config
from .crawl import Excluder
from .indexer import QOS_BACKGROUND, Indexer, set_thread_qos

DEBOUNCE_S = 2.0
RESCAN_EVERY_S = 6 * 3600  # catches events FSEvents dropped (sleep, unmounted volumes)


def start_watcher(cfg: Config, indexer: Indexer) -> bool:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        return False

    pending: set[str] = set()
    lock = threading.Lock()
    wake = threading.Event()
    ex = Excluder(cfg)
    roots = cfg.root_paths

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.event_type in ("opened", "closed_no_write"):
                return
            paths = [event.src_path] + ([event.dest_path] if getattr(event, "dest_path", None) else [])
            with lock:
                for p in paths:
                    p = p.decode() if isinstance(p, bytes) else p
                    # Folder events must pass even if the leaf is a folder name we skip, so deletions propagate.
                    if not ex.excluded(p, roots) or event.is_directory:
                        pending.add(p)
            wake.set()

    observer = Observer()
    handler = Handler()
    watched = 0
    for r in roots:
        if r.is_dir():
            observer.schedule(handler, str(r), recursive=True)
            watched += 1
    if not watched:
        return False
    observer.daemon = True
    observer.start()

    def loop():
        set_thread_qos(QOS_BACKGROUND)
        last_rescan = time.monotonic()
        while True:
            wake.wait(timeout=60)
            # Debounce: wait until events stop arriving for DEBOUNCE_S.
            while wake.is_set():
                wake.clear()
                time.sleep(DEBOUNCE_S)
            with lock:
                batch = set(pending)
                pending.clear()
            if not db.get_meta("last_index"):
                continue  # no index yet (first launch, or index deleted): wait for the button on the page
            if batch and not indexer.lock.locked():
                try:
                    with indexer.lock:
                        indexer.update_paths(batch)
                except Exception as e:  # noqa: BLE001 - the watcher must survive any file
                    print(f"watcher: {type(e).__name__}: {e}", file=sys.stderr)
            elif batch:
                with lock:
                    pending.update(batch)  # a full run is going; retry after it
            if time.monotonic() - last_rescan > RESCAN_EVERY_S and not indexer.lock.locked() and db.get_meta("last_index"):
                last_rescan = time.monotonic()
                try:
                    indexer.run(qos=QOS_BACKGROUND)
                except Exception as e:  # noqa: BLE001
                    print(f"rescan: {type(e).__name__}: {e}", file=sys.stderr)

    threading.Thread(target=loop, name="watcher", daemon=True).start()
    return True
