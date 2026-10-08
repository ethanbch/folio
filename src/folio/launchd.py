"""Start folio at login with a launchd agent."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from .config import data_path

LABEL = "com.github.ethanbch.folio"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def _program() -> list[str]:
    """The command launchd runs: the folio launcher if on PATH, else this Python."""
    exe = shutil.which("folio")
    if exe:
        return [exe, "serve"]
    return [sys.executable, "-m", "folio", "serve"]


def install() -> int:
    log = data_path("server.log")
    plist = {
        "Label": LABEL,
        "ProgramArguments": _program(),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        # Standard, so searches answer at full speed. Indexing threads lower their own priority
        # (QoS utility or background) and extraction runs in processes at nice 10.
        "ProcessType": "Standard",
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONUNBUFFERED": "1",
            # The npm launcher runs folio from its package folder; launchd must find it the same way.
            **{k: os.environ[k] for k in ("PYTHONPATH", "FOLIO_DATA_DIR") if k in os.environ},
        },
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)], capture_output=True)
    with open(PLIST, "wb") as f:
        plistlib.dump(plist, f)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"launchctl bootstrap failed: {r.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"Installed {PLIST}. folio now starts at login. Log: {log}")
    return 0


def uninstall() -> int:
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)], capture_output=True)
    if PLIST.exists():
        PLIST.unlink()
        print(f"Removed {PLIST}.")
    else:
        print("No launchd agent installed.")
    return 0


def status() -> int:
    r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], capture_output=True, text=True)
    if r.returncode != 0:
        print("Not installed.")
        return 1
    state = next((l.strip() for l in r.stdout.splitlines() if l.strip().startswith("state =")), "state = unknown")
    print(f"Installed ({PLIST}), {state}.")
    return 0


def main(action: str) -> int:
    return {"install": install, "uninstall": uninstall, "status": status}[action]()
