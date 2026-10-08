"""Configuration: defaults, then ~/Library/Application Support/folio/config.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

HOME = Path.home()
DATA_DIR = Path(os.environ.get("FOLIO_DATA_DIR", HOME / "Library/Application Support/folio"))
ICLOUD_DIR = HOME / "Library/Mobile Documents/com~apple~CloudDocs"

DEFAULT_CONFIG = """\
# folio configuration. Edit, then run `folio reindex` if you change roots or exclusions.

# Folders to index. "~" is expanded.
roots = ["~/Documents", "~/Desktop", "~/Downloads"]

# Also index iCloud Drive. Files not downloaded are indexed by name and path only.
icloud = true

# Folder names skipped anywhere in the tree.
exclude_dirs = [
  ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__",
  "site-packages", "dist-packages", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
  ".cache", "Caches", "cache", ".Trash", ".next", ".nuxt", "build", "target", ".gradle",
  ".idea", ".vscode", "DerivedData", "Pods", ".npm", ".yarn", "bower_components",
  ".ipynb_checkpoints", "Library", ".DocumentRevisions-V100", ".Spotlight-V100",
  ".fseventsd", ".TemporaryItems", "$RECYCLE.BIN", "Photos Library.photoslibrary",
  "Music Library.musiclibrary",
]

# Glob patterns on file names that are never indexed.
exclude_files = [
  ".DS_Store", "*.pyc", "*.pyo", "*.o", "*.so", "*.dylib", "*.class", "*.tmp", "~$*",
  "*.swp", ".localized", "Icon\\r", "*.crdownload", "*.part", "*.lock",
  # LaTeX build files
  "*.aux", "*.fls", "*.fdb_latexmk", "*.synctex.gz", "*.bbl", "*.blg", "*.toc", "*.lof", "*.lot", "*.nav", "*.snm", "*.vrb",
  # Secrets: never indexed, so never shown in an excerpt
  "kaggle.json", "*.pem", "*.p12", "*.pfx", "*.kdbx", "id_rsa*", "id_ed25519*", "credentials*.json", "*secret*.json",
  "*.keychain", "*.keychain-db", "*.ovpn",
]

# Content is not extracted from files larger than this (name and path are still indexed).
max_content_mb = 50

# Characters of extracted text kept per file.
max_content_chars = 200000

# Seconds before an extraction is abandoned.
extract_timeout_s = 20

# Embedding model: "e5-small" (default), "e5-base".
embedding_model = "e5-small"

# Chunks embedded per file: ≈ 4 000 tokens, the first pages. The full text stays searchable by keywords.
max_chunks_per_file = 16

# Re-rank the top 10 with a cross-encoder (≈ 80 ms, ≈ 135 MB of memory). Measured gain in docs/EVAL.md.
rerank = true

# Port of the local server (listens on 127.0.0.1 only).
port = 7381

# Indexing pauses when on battery below this percentage.
min_battery_percent = 20
"""


@dataclass
class Config:
    roots: list[str] = field(default_factory=lambda: ["~/Documents", "~/Desktop", "~/Downloads"])
    icloud: bool = True
    exclude_dirs: list[str] = field(default_factory=list)
    exclude_files: list[str] = field(default_factory=list)
    max_content_mb: float = 50
    max_content_chars: int = 200_000
    extract_timeout_s: float = 20
    embedding_model: str = "e5-small"
    max_chunks_per_file: int = 16
    rerank: bool = True
    port: int = 7381
    min_battery_percent: int = 20

    @property
    def root_paths(self) -> list[Path]:
        paths = [Path(os.path.expanduser(r)).resolve() for r in self.roots]
        if self.icloud and ICLOUD_DIR.is_dir():
            paths.append(ICLOUD_DIR)
        # Drop roots nested in another root.
        unique = []
        for p in sorted(set(paths), key=lambda p: len(p.parts)):
            if not any(p.is_relative_to(u) for u in unique):
                unique.append(p)
        return unique


def config_path() -> Path:
    return DATA_DIR / "config.toml"


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG)
    values = tomllib.loads(DEFAULT_CONFIG)
    values.update(tomllib.loads(path.read_text()))
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in values.items() if k in known})


def data_path(*parts: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR.joinpath(*parts)
