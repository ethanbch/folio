"""Local ONNX models: download once into the data folder, then load offline."""

from __future__ import annotations

import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import data_path

HF = "https://huggingface.co/{repo}/resolve/{rev}/{file}"

# Called with (label, bytes done, bytes total) while a model downloads; set by the indexer for the page.
DOWNLOAD_HOOK = None


@dataclass(frozen=True)
class ModelSpec:
    key: str
    repo: str
    rev: str
    onnx: str
    dim: int
    query_prefix: str = ""
    passage_prefix: str = ""
    max_tokens: int = 320  # chunks are ≈ 250 tokens; dense tables can reach 512, which costs 2.5× the time and memory


# Both models use the XLM-RoBERTa vocabulary. sentencepiece reads it in ≈ 65 MB of memory;
# the Hugging Face tokenizers library needs ≈ 390 MB for the same 250 002 entries.
VOCAB = ("intfloat/multilingual-e5-small", "main", "sentencepiece.bpe.model")

EMBEDDERS = {
    "e5-small": ModelSpec("e5-small", "Xenova/multilingual-e5-small", "main", "onnx/model_quantized.onnx", 384, "query: ", "passage: "),
    "e5-base": ModelSpec("e5-base", "Xenova/multilingual-e5-base", "main", "onnx/model_quantized.onnx", 768, "query: ", "passage: "),
}

RERANKERS = {
    "mmarco-minilm": ModelSpec(
        "mmarco-minilm", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", "main", "onnx/model_qint8_arm64.onnx", 1, max_tokens=512
    ),
}


def model_dir(spec: ModelSpec) -> Path:
    return data_path("models", spec.key)


def ensure_model(spec: ModelSpec, allow_download: bool = True) -> Path:
    """Files of a model, downloaded on first use. The only network access folio makes."""
    d = model_dir(spec)
    d.mkdir(parents=True, exist_ok=True)
    _fetch(spec.repo, spec.rev, spec.onnx, d / "model.onnx", allow_download, spec.key)
    _fetch(*VOCAB, vocab_path(), allow_download, "vocabulary")
    return d


def missing_files(embedder: str, rerank: bool) -> int:
    """How many model files a first run downloads."""
    specs = [EMBEDDERS[embedder]] + ([RERANKERS["mmarco-minilm"]] if rerank else [])
    return sum(not (model_dir(s) / "model.onnx").exists() for s in specs) + (not vocab_path().exists())


def vocab_path() -> Path:
    return data_path("models", "xlm-roberta.spm")


def _fetch(repo: str, rev: str, remote: str, target: Path, allow_download: bool, label: str) -> None:
    if target.exists():
        return
    if not allow_download:
        raise FileNotFoundError(f"Model file {target.name} ({label}) is missing. Run `folio models` to download it.")
    url = HF.format(repo=repo, rev=rev, file=remote)
    print(f"Downloading {label}: {remote}", file=sys.stderr)
    tmp = target.with_suffix(".part")

    def hook(blocks: int, block_size: int, total: int) -> None:
        if DOWNLOAD_HOOK:
            DOWNLOAD_HOOK(label, min(blocks * block_size, total) if total > 0 else blocks * block_size, max(total, 0))

    urllib.request.urlretrieve(url, tmp, reporthook=hook)
    tmp.rename(target)


def _session(path: Path, threads: int):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.enable_cpu_mem_arena = False  # keeps resident memory close to the model size
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


class XLMRTokenizer:
    """XLM-RoBERTa ids from the sentencepiece model: fairseq ids are sentencepiece ids + 1, unknown is 3."""

    _shared: dict[str, object] = {}

    def __init__(self, max_tokens: int):
        import sentencepiece as spm

        key = str(vocab_path())
        if key not in self._shared:
            self._shared[key] = spm.SentencePieceProcessor(model_file=key)
        self.sp = self._shared[key]
        self.max_tokens = max_tokens

    def _ids(self, text: str) -> list[int]:
        return [3 if i == 0 else i + 1 for i in self.sp.encode(text)]

    def encode(self, text: str) -> list[int]:
        return [0] + self._ids(text)[: self.max_tokens - 2] + [2]

    def encode_pair(self, a: str, b: str) -> list[int]:
        ia = self._ids(a)[: self.max_tokens // 2]
        ib = self._ids(b)[: max(1, self.max_tokens - len(ia) - 4)]
        return [0] + ia + [2, 2] + ib + [2]


def _batch(seqs: list[list[int]]):
    n = max(len(x) for x in seqs)
    ids = np.ones((len(seqs), n), dtype=np.int64)  # 1 = <pad>
    mask = np.zeros((len(seqs), n), dtype=np.int64)
    for i, x in enumerate(seqs):
        ids[i, : len(x)] = x
        mask[i, : len(x)] = 1
    return ids, mask, np.zeros_like(ids)


class Embedder:
    def __init__(self, key: str = "e5-small", threads: int = 2, allow_download: bool = True):
        self.spec = EMBEDDERS[key]
        d = ensure_model(self.spec, allow_download)
        self.session = _session(d / "model.onnx", threads)
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.tok = XLMRTokenizer(self.spec.max_tokens)
        self.dim = self.spec.dim

    def tokens(self, text: str) -> int:
        return len(self.tok._ids(text))

    def _run(self, texts: list[str]) -> np.ndarray:
        ids, mask, types = _batch([self.tok.encode(t) for t in texts])
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = types
        hidden = self.session.run(None, feed)[0]
        m = mask[..., None].astype(np.float32)
        vec = (hidden * m).sum(1) / np.maximum(m.sum(1), 1e-9)  # mean pooling
        return vec / np.maximum(np.linalg.norm(vec, axis=1, keepdims=True), 1e-9)

    def embed_passages(self, texts: list[str], batch: int = 8) -> np.ndarray:
        out = []
        # Sort by length so each batch pads little.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        for s in range(0, len(order), batch):
            idx = order[s : s + batch]
            out.append((idx, self._run([self.spec.passage_prefix + texts[i] for i in idx])))
        result = np.zeros((len(texts), self.dim), dtype=np.float32)
        for idx, vecs in out:
            result[idx] = vecs
        return result

    def embed_query(self, text: str) -> np.ndarray:
        return self._run([self.spec.query_prefix + text])[0]


class Reranker:
    def __init__(self, key: str = "mmarco-minilm", threads: int = 4, allow_download: bool = True):
        self.spec = RERANKERS[key]
        d = ensure_model(self.spec, allow_download)
        self.session = _session(d / "model.onnx", threads)
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.tok = XLMRTokenizer(256)

    def score(self, query: str, passages: list[str]) -> np.ndarray:
        if not passages:
            return np.zeros(0, dtype=np.float32)
        ids, mask, types = _batch([self.tok.encode_pair(query, p) for p in passages])
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = types
        logits = self.session.run(None, feed)[0]
        return logits.reshape(len(passages), -1)[:, 0].astype(np.float32)


def threads_for_indexing() -> int:
    return max(1, min(4, (os.cpu_count() or 4) // 3))
