"""folio doctor and folio status."""

from __future__ import annotations

import os
import platform
import shutil
import time

from . import __version__, db, macos
from .config import DATA_DIR, config_path, load_config
from .models import EMBEDDERS, RERANKERS, model_dir

OK, WARN, FAIL = "ok  ", "warn", "FAIL"


def _line(level: str, label: str, detail: str = "") -> None:
    print(f"[{level}] {label}" + (f": {detail}" if detail else ""))


def doctor() -> int:
    cfg = load_config()
    failures = 0
    print(f"folio {__version__} · Python {platform.python_version()} · macOS {platform.mac_ver()[0]} · {platform.machine()}")

    if macos.has_full_disk_access():
        _line(OK, "Full Disk Access", "granted to the process running folio")
    else:
        _line(
            WARN,
            "Full Disk Access",
            "not granted. Folders under ~/Library and some app folders are skipped. "
            "Grant it in System Settings › Privacy & Security › Full Disk Access to the terminal (or app) that runs folio.",
        )

    for root in cfg.root_paths:
        try:
            os.listdir(root)
            _line(OK, "Folder readable", str(root))
        except PermissionError:
            failures += 1
            _line(FAIL, "Folder not readable", f"{root}. Grant Full Disk Access, or allow folio in Files and Folders.")
        except FileNotFoundError:
            _line(WARN, "Folder missing", str(root))

    for spec in (EMBEDDERS[cfg.embedding_model], RERANKERS["mmarco-minilm"]):
        d = model_dir(spec)
        if (d / "model.onnx").exists():
            size = (d / "model.onnx").stat().st_size / 1e6
            _line(OK, f"Model {spec.key}", f"{size:.0f} MB in {d}")
        elif spec in RERANKERS.values() and not cfg.rerank:
            _line(OK, f"Model {spec.key}", "not downloaded (only needed with rerank = true)")
        else:
            _line(WARN, f"Model {spec.key}", "not downloaded yet. It is downloaded on the first indexing, or with `folio models`.")

    try:
        conn = db.connect()
        n = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        errors = conn.execute("SELECT COUNT(*) FROM files WHERE status IN ('error', 'timeout')").fetchone()[0]
        last = db.get_meta("last_index")
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(last))) if last else "never"
        _line(OK if n else WARN, "Index", f"{n} files, {errors} read errors, last run {when}")
    except Exception as e:  # noqa: BLE001
        failures += 1
        _line(FAIL, "Index", f"{type(e).__name__}: {e}")

    free = shutil.disk_usage(DATA_DIR).free / 1e9
    used = sum(f.stat().st_size for f in DATA_DIR.rglob("*") if f.is_file()) / 1e6
    _line(OK if free > 2 else WARN, "Disk", f"folio uses {used:.0f} MB in {DATA_DIR}; {free:.1f} GB free")

    on_batt, pct = macos.battery()
    if on_batt and pct is not None and pct < cfg.min_battery_percent:
        _line(WARN, "Battery", f"{pct} %: indexing pauses below {cfg.min_battery_percent} %")

    from .launchd import PLIST

    _line(OK, "Start at login", "installed" if PLIST.exists() else "not installed (`folio agent install`)")
    print(f"Configuration: {config_path()}")
    return 1 if failures else 0


def status() -> int:
    conn = db.connect()
    for status, n in conn.execute("SELECT status, COUNT(*) FROM files GROUP BY status ORDER BY 2 DESC"):
        print(f"{status:10} {n}")
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"{'vectors':10} {chunks}")
    return 0
