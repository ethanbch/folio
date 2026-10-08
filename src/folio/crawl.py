"""Directory walk with exclusions."""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .config import Config

# Directories macOS shows as a single file.
PACKAGE_EXTS = {"pages", "numbers", "key", "rtfd", "app", "band", "logicx", "scriv", "sketch", "graffle", "playground"}
# Directories skipped by suffix.
SKIP_SUFFIXES = (
    ".framework",
    ".bundle",
    ".photoslibrary",
    ".musiclibrary",
    ".xcodeproj",
    ".xcworkspace",
    ".lproj",
    ".egg-info",
    ".dist-info",
    ".plugin",
    ".kext",
)


@dataclass(slots=True)
class Entry:
    path: str
    stat: os.stat_result
    is_package: bool = False


class Excluder:
    def __init__(self, cfg: Config):
        self.dirs = set(cfg.exclude_dirs)
        pattern = "|".join(fnmatch.translate(p) for p in cfg.exclude_files) or "(?!)"
        self.files = re.compile(pattern)

    def skip_dir(self, name: str, path: str) -> bool:
        if name in self.dirs or name.startswith(".") or name.endswith(SKIP_SUFFIXES):
            return True
        # Python virtual environments, whatever their name.
        return os.path.exists(os.path.join(path, "pyvenv.cfg"))

    def skip_file(self, name: str) -> bool:
        return name.startswith(".") or bool(self.files.match(name))

    def excluded(self, path: str, roots: list[Path]) -> bool:
        """True if a path (from the watcher) falls under an excluded folder or name."""
        p = Path(path)
        root = next((r for r in roots if p.is_relative_to(r)), None)
        if root is None:
            return True
        parts = p.relative_to(root).parts
        for i, part in enumerate(parts[:-1]):
            if self.skip_dir(part, str(root.joinpath(*parts[: i + 1]))):
                return True
        return self.skip_file(p.name)


def walk(cfg: Config) -> Iterator[Entry]:
    ex = Excluder(cfg)
    for root in cfg.root_paths:
        stack = [str(root)]
        while stack:
            current = stack.pop()
            try:
                it = os.scandir(current)
            except OSError:
                continue
            with it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            ext = e.name.rsplit(".", 1)[-1].lower() if "." in e.name else ""
                            if ext in PACKAGE_EXTS and not e.name.startswith("."):
                                yield Entry(e.path, e.stat(follow_symlinks=False), True)
                            elif not ex.skip_dir(e.name, e.path):
                                stack.append(e.path)
                        elif e.is_file(follow_symlinks=False) and not ex.skip_file(e.name):
                            yield Entry(e.path, e.stat(follow_symlinks=False))
                    except OSError:
                        continue
