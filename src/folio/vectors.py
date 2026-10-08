"""Vector store: int8 vectors with a per-row scale, in an append-only file read through mmap.

Search is brute force: below ~200 k rows a matrix product is faster than an
approximate index and gives exact results.
"""

from __future__ import annotations

import os
import threading

import numpy as np

from .config import data_path


class VectorStore:
    def __init__(self, dim: int, model_key: str):
        self.dim = dim
        self.dir = data_path("vectors", model_key)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.vec_path = self.dir / "vectors.i8"
        self.scale_path = self.dir / "scales.f32"
        self.lock = threading.Lock()
        self.owner = np.zeros(0, dtype=np.int64)  # file id per row, -1 when dead
        self._load()

    def _load(self) -> None:
        rows = self.scale_path.stat().st_size // 4 if self.scale_path.exists() else 0
        if self.vec_path.exists() and self.vec_path.stat().st_size != rows * self.dim:
            rows = min(rows, self.vec_path.stat().st_size // self.dim)
        self.rows = rows
        if rows:
            self.vecs = np.memmap(self.vec_path, dtype=np.int8, mode="r", shape=(rows, self.dim))
            self.scales = np.fromfile(self.scale_path, dtype=np.float32, count=rows)
        else:
            self.vecs = np.zeros((0, self.dim), dtype=np.int8)
            self.scales = np.zeros(0, dtype=np.float32)
        if len(self.owner) != rows:
            owner = np.full(rows, -1, dtype=np.int64)
            owner[: min(rows, len(self.owner))] = self.owner[:rows]
            self.owner = owner

    def set_owners(self, pairs) -> None:
        """pairs: iterable of (row, file_id) for live rows."""
        owner = np.full(self.rows, -1, dtype=np.int64)
        for row, fid in pairs:
            if row < self.rows:
                owner[row] = fid
        self.owner = owner

    def append(self, vecs: np.ndarray, file_id: int) -> list[int]:
        """Quantize and append. Returns the new row numbers."""
        if len(vecs) == 0:
            return []
        maxabs = np.maximum(np.abs(vecs).max(axis=1), 1e-9)
        q = np.round(vecs / maxabs[:, None] * 127).astype(np.int8)
        scales = (maxabs / 127).astype(np.float32)
        with self.lock:
            start = self.rows
            with open(self.vec_path, "ab") as f:
                f.write(q.tobytes())
            with open(self.scale_path, "ab") as f:
                f.write(scales.tobytes())
            self._load()
            self.owner[start : start + len(vecs)] = file_id
        return list(range(start, start + len(vecs)))

    def kill(self, rows: list[int]) -> None:
        with self.lock:
            for r in rows:
                if r < self.rows:
                    self.owner[r] = -1

    def search(self, query: np.ndarray, limit: int, allowed: np.ndarray | None = None) -> list[tuple[int, int, float]]:
        """Top rows as (row, file_id, cosine). `allowed`: boolean mask over file ids."""
        vecs, scales, owner = self.vecs, self.scales, self.owner
        n = min(len(owner), len(scales))
        if n == 0:
            return []
        scores = np.empty(n, dtype=np.float32)
        step = 32768
        for s in range(0, n, step):
            block = np.asarray(vecs[s : s + step], dtype=np.float32)
            scores[s : s + step] = block @ query
        scores *= scales[:n]
        live = owner[:n] >= 0
        if allowed is not None:
            ok = np.zeros(n, dtype=bool)
            idx = np.where(live)[0]
            fids = owner[idx]
            inside = fids < len(allowed)
            ok[idx[inside]] = allowed[fids[inside]]
            live = ok
        scores[~live] = -np.inf
        k = min(limit, int(live.sum()))
        if k <= 0:
            return []
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(r), int(owner[r]), float(scores[r])) for r in top]

    def dead_ratio(self) -> float:
        return float((self.owner < 0).mean()) if len(self.owner) else 0.0

    def compact(self, rows_by_file: dict[int, list[int]]) -> dict[int, int]:
        """Rewrite the file with live rows only. Returns old row → new row."""
        with self.lock:
            mapping, new_vecs, new_scales = {}, [], []
            for rows in rows_by_file.values():
                for r in rows:
                    if r < self.rows:
                        mapping[r] = len(mapping)
                        new_vecs.append(np.asarray(self.vecs[r]))
                        new_scales.append(self.scales[r])
            tmp_v, tmp_s = self.vec_path.with_suffix(".tmp"), self.scale_path.with_suffix(".tmp")
            np.asarray(new_vecs, dtype=np.int8).reshape(-1, self.dim).tofile(tmp_v)
            np.asarray(new_scales, dtype=np.float32).tofile(tmp_s)
            os.replace(tmp_v, self.vec_path)
            os.replace(tmp_s, self.scale_path)
            self.owner = np.zeros(0, dtype=np.int64)
            self._load()
            return mapping
