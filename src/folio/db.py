"""SQLite store: file metadata, indexing state, chunks, and the local search log."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .config import data_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  ext TEXT NOT NULL,
  kind TEXT NOT NULL,
  size INTEGER NOT NULL,
  mtime REAL NOT NULL,
  ctime REAL NOT NULL,
  last_used REAL,
  dataless INTEGER NOT NULL DEFAULT 0,
  -- pending: content not extracted yet; ok, empty, skipped, too_big, dataless, error, timeout
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  content_chars INTEGER NOT NULL DEFAULT 0,
  lexical_mtime REAL,          -- mtime the lexical index reflects
  embedded_mtime REAL,         -- mtime the vectors reflect
  seen INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS files_status ON files(status);
CREATE INDEX IF NOT EXISTS files_mtime ON files(mtime);

CREATE TABLE IF NOT EXISTS chunks (
  row INTEGER PRIMARY KEY,     -- row in the vector file
  file_id INTEGER NOT NULL,
  start INTEGER NOT NULL,      -- character offsets in the stored content
  end INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file_id);

CREATE TABLE IF NOT EXISTS searches (
  id INTEGER PRIMARY KEY,
  ts REAL NOT NULL,
  query TEXT NOT NULL,
  results INTEGER NOT NULL,
  ms REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS clicks (
  id INTEGER PRIMARY KEY,
  ts REAL NOT NULL,
  query TEXT NOT NULL,
  file_id INTEGER NOT NULL,
  path TEXT NOT NULL,
  rank INTEGER NOT NULL,
  action TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS clicks_file ON clicks(file_id);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

_local = threading.local()


def db_file() -> Path:
    return data_path("folio.db")


def connect() -> sqlite3.Connection:
    """One connection per thread."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(db_file(), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA)
        _local.conn = conn
    return conn


def get_meta(key: str, default: str | None = None) -> str | None:
    row = connect().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(key: str, value: str) -> None:
    conn = connect()
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))
    conn.commit()
