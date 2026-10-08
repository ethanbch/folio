"""macOS helpers: extended attributes, iCloud placeholders, battery, permissions, Finder actions."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import struct
import subprocess
from pathlib import Path

SF_DATALESS = 0x40000000  # iCloud file whose content is not on disk
_LAST_USED = b"com.apple.lastuseddate#PS"

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
_libc.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
_libc.getxattr.restype = ctypes.c_ssize_t
_XATTR_NOFOLLOW = 0x0001


def last_used(path: str) -> float | None:
    """Last time the file was opened (the value behind kMDItemLastUsedDate), in seconds."""
    buf = ctypes.create_string_buffer(16)
    n = _libc.getxattr(os.fsencode(path), _LAST_USED, buf, 16, 0, _XATTR_NOFOLLOW)
    if n != 16:
        return None
    sec, nsec = struct.unpack("<qq", buf.raw)
    return sec + nsec / 1e9 if sec > 0 else None


def is_dataless(st: os.stat_result) -> bool:
    return bool(getattr(st, "st_flags", 0) & SF_DATALESS)


def battery() -> tuple[bool, int | None]:
    """(on_battery, percent). Desktop Macs return (False, None)."""
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False, None
    pct = re.search(r"(\d+)%", out)
    return "Battery Power" in out, int(pct.group(1)) if pct else None


def has_full_disk_access() -> bool:
    """The user TCC database is readable only with Full Disk Access."""
    tcc = Path.home() / "Library/Application Support/com.apple.TCC/TCC.db"
    try:
        with open(tcc, "rb") as f:
            f.read(16)
        return True
    except OSError:
        return False


def open_file(path: str) -> None:
    subprocess.Popen(["open", "--", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def reveal(path: str) -> None:
    subprocess.Popen(["open", "-R", "--", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_quicklook: subprocess.Popen | None = None


def quicklook(path: str) -> None:
    """Show a Quick Look panel; a second call closes the previous one."""
    global _quicklook
    if _quicklook and _quicklook.poll() is None:
        _quicklook.terminate()
    _quicklook = subprocess.Popen(["qlmanage", "-p", "--", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def set_background_priority() -> None:
    """Lowest CPU priority and throttled disk I/O for the current process."""
    try:
        os.nice(10)
    except OSError:
        pass
    try:
        # setiopolicy_np(IOPOL_TYPE_DISK, IOPOL_SCOPE_PROCESS, IOPOL_THROTTLE)
        _libc.setiopolicy_np(0, 0, 3)
    except AttributeError:
        pass
