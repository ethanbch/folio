"""folio reset (delete the index) and folio uninstall (delete everything folio created)."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .config import DATA_DIR

# What `reset` deletes: the index. Models, configuration and evaluation queries stay.
INDEX_ITEMS = ["folio.db", "folio.db-wal", "folio.db-shm", "tantivy", "vectors"]


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())


def _mb(n: int) -> str:
    return f"{n / 1e6:,.0f} MB".replace(",", " ")


def _confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        print("Add --yes to confirm when not running in a terminal.", file=sys.stderr)
        return False
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes", "o", "oui")


def _agent_serves_this_folder() -> bool:
    """True if the launchd agent runs folio on this data folder (FOLIO_DATA_DIR can point elsewhere)."""
    import plistlib

    from .config import HOME
    from .launchd import PLIST

    if not PLIST.exists():
        return False
    env = plistlib.loads(PLIST.read_bytes()).get("EnvironmentVariables", {})
    folder = Path(env.get("FOLIO_DATA_DIR", HOME / "Library/Application Support/folio"))
    return folder.resolve() == DATA_DIR.resolve()


def _ask_server(path: str) -> bool:
    """Runs an action through the server of this data folder, if one is running."""
    import json
    import urllib.request

    from .config import load_config

    token = DATA_DIR / "server.token"
    if not token.exists():
        return False
    port = load_config().port
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json", "X-Folio-Token": token.read_text().strip(), "Origin": f"http://127.0.0.1:{port}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("ok", False)
    except OSError:
        return False


def _stop_server() -> None:
    """Stops the folio server of this data folder: its launchd agent, or the process in server.pid."""
    from .launchd import LABEL

    if _agent_serves_this_folder():
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    pid_file = DATA_DIR / "server.pid"
    try:
        pid = int(pid_file.read_text())
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):  # up to 5 s
            time.sleep(0.1)
            os.kill(pid, 0)
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        pass


def reset(yes: bool = False) -> int:
    items = [DATA_DIR / name for name in INDEX_ITEMS if (DATA_DIR / name).exists()]
    if not items:
        print("No index to delete.")
        return 0
    total = sum(_size(p) for p in items)
    print(f"This deletes the index and the search history in {DATA_DIR} ({_mb(total)}).")
    print("Your files are not touched. Models and configuration stay, so the next indexing downloads nothing.")
    if not _confirm("Delete the index?", yes):
        print("Nothing deleted.")
        return 1
    if _ask_server("/api/reset"):
        print(f"Index deleted ({_mb(total)} freed). Open the page to index again.")
        return 0
    _stop_server()
    for p in items:
        shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
    print(f"Index deleted ({_mb(total)} freed). Run `folio` to index again.")
    return 0


def uninstall(yes: bool = False) -> int:
    from .launchd import PLIST

    agent = _agent_serves_this_folder()
    total = _size(DATA_DIR) if DATA_DIR.exists() else 0
    print("This deletes everything folio created on this Mac:")
    print(f"  {DATA_DIR}  ({_mb(total)}: index, models, configuration, search log, Python environment)")
    if agent:
        print(f"  {PLIST}  (start at login)")
    print("Your own files are not touched.")
    if not _confirm("Uninstall folio?", yes):
        print("Nothing deleted.")
        return 1
    _stop_server()
    if agent:
        PLIST.unlink(missing_ok=True)
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    print(f"Deleted ({_mb(total)} freed).")
    print("To remove the command itself: npm uninstall -g folio-search")
    return 0
