# Evaluation

Every ranking decision in folio is settled by `folio eval`, on a set of queries
with known answers, not by intuition. This file keeps the variants tested and
what they showed.

## Method

- **Queries.** 61 queries in French, written the way one remembers a file:
  partial, by topic, client, course or folder, rarely by exact name. Each
  query lists every copy of the expected file (`(1)`, `(2)`, the Downloads
  copy of a Documents file…); any of them counts as found.
- **Metrics.** MRR (mean of 1/rank of the first expected file), recall@1/3/10
  (share of queries with an expected file in the top 1, 3, 10), and latency
  p50/p95 of `Engine.search`, index warm.
- **Index.** 4 408 files on an M3 MacBook Air (8 GB): 950 with readable
  content, 3 458 stored in iCloud and not downloaded, so indexed by name and
  folder only.
- **Noise.** With 61 queries, one query is 1.6 points of recall and ≈ 0.016 of
  MRR. Differences smaller than that are treated as noise.
- **Run it.** `folio eval --preset phases|weights|rerank --markdown`, or
  `--variant name=key:value,…` for any knob of `engine.Options`. The query file
  lives in the data folder (`queries.jsonl`), outside the repository, because
  it names real files.

Limits of this set: the queries were written after looking at a sample of
files, so they lean toward words that appear in names. Queries logged from
real use (`folio export-log`) will correct that bias.

## Phases

Each line adds one stage to the previous one. Final defaults (`rrf_k` 20,
soft filters, reranker on the top 10).

| Variant | MRR | R@1 | R@3 | R@10 | p50 | p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 · keywords, names and folders | 0.661 | 59% | 70% | 80% | 1 ms | 2 ms |
| 2 · keywords + content | 0.687 | 57% | 79% | 87% | 4 ms | 7 ms |
| 3 · hybrid (RRF) | 0.724 | 62% | 79% | 87% | 7 ms | 9 ms |
| 4 · + dates and types | 0.736 | 66% | 77% | 87% | 7 ms | 10 ms |
| 4 · + signals | 0.755 | 67% | 82% | 89% | 10 ms | 12 ms |
| 4 · + reranker | 0.783 | 70% | 84% | 89% | 59 ms | 72 ms |

- Content adds 9 points of recall@3 over names and folders alone.
- Meaning (embeddings) adds 0.04 MRR on top of keywords.
- Dates and types read from the query, then ranking signals, add 0.03 MRR.
- The reranker adds 0.03 MRR and 3 points of recall@1, for ≈ 80 ms.

## Decisions

### Fusion constant `rrf_k`: 20, not 60

The first hybrid run ranked **below** keywords alone (MRR 0.642 vs 0.687 with
`rrf_k` 60). With few strong matches per query, a large `k` flattens the gap
between rank 1 and rank 10 of each list, and the semantic list, noisier at the
top, pulled good keyword hits down.

| `rrf_k` | MRR | R@1 | R@3 | R@10 |
| --- | --- | --- | --- | --- |
| 10 | 0.756 | 67% | 82% | 90% |
| 20 | 0.755 | 67% | 82% | 89% |
| 40 | 0.688 | 59% | 75% | 85% |
| 60 | 0.665 | 56% | 74% | 84% |

10 and 20 are equal within noise; 20 is kept as the less extreme value.

### Dates and types from the query: rank, don't exclude

As hard filters, they lost queries. A query starting with "présentation sur…"
excluded the PDF that was expected, because "présentation" set the type to
slides. A query ending with a month and a year ("… mai 2022") excluded a file
whose name holds that date (`…_202205.pdf`) but which was modified years
later. Two changes:

1. Dates and types from the query raise matching files (+0.4) and lower the
   others (−0.2) instead of excluding them. The filters picked with the
   buttons in the interface stay strict.
2. Type words that are also ordinary words ("présentation", "slides",
   "notebook", "photo"…) stay in the searched text; format words ("pdf",
   "excel", "docx") leave it. "mai 2022" also searches `2022 05` in names.

| Variant | MRR | R@1 | R@3 | R@10 |
| --- | --- | --- | --- | --- |
| Hard filters | 0.607 | 48% | 72% | 82% |
| Soft filters | 0.660 | 54% | 75% | 85% |

(Measured before the `rrf_k` change; both lines use `rrf_k` 60.)

### Keywords: one list, not two

Files known by name only (iCloud placeholders) seemed buried under files with
text. Hypothesis: rank names-and-folders and content as two separate lists in
the fusion. Measured, it lost:

| Variant | MRR | R@1 | R@3 | R@10 |
| --- | --- | --- | --- | --- |
| One list (name ×3, folders ×1.5, content ×1) | 0.755 | 67% | 82% | 89% |
| Two lists | 0.727 | 64% | 79% | 87% |

Kept: one list.

### Name vectors: essential

Each file has a vector for its name and folders, on top of its content
chunks. Without them, MRR drops from ≈ 0.73 to ≈ 0.51: three quarters of the
files have no content to embed.

### Weights that changed nothing measurable

Name ×5 instead of ×3, folders ×3 instead of ×1.5, content ×0.5, semantic
weight 0.5 to 2, the multi-chunk bonus, the exact-name bonus and recency
between 0 and 0.15 all moved MRR by less than 0.02. Defaults stay as they
were. Doubling recency (0.3) lowered MRR by 0.04: most expected files are
not recent.

### Reranker: on, top 10, 150 characters

[mmarco-mMiniLMv2-L12-H384](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1),
int8, re-scores the top results with the query. Its cost grows with the number
and length of passages; quality did not drop with shorter passages.

| Variant | MRR | R@1 | R@3 | R@10 | p50 | p95 |
| --- | --- | --- | --- | --- | --- | --- |
| no reranker | 0.755 | 67% | 82% | 89% | 10 ms | 12 ms |
| top 20, 600 chars | 0.775 | 69% | 84% | 89% | 349 ms | 388 ms |
| top 20, 300 chars | 0.775 | 69% | 84% | 89% | 202 ms | 339 ms |
| top 10, 300 chars | 0.780 | 70% | 84% | 89% | 96 ms | 131 ms |
| top 10, 150 chars | 0.783 | 70% | 84% | 89% | 67 ms | 81 ms |
| top 10, 150 chars, weight 0.5 | 0.775 | 69% | 84% | 89% | 69 ms | 85 ms |
| top 10, 150 chars, weight 2 | 0.775 | 70% | 80% | 89% | 68 ms | 82 ms |

Kept: top 10, 150 characters (file name, folder, and the best excerpt). The
interface shows the fast list at once and replaces it with the re-ranked list
about 80 ms later.

### Embedding model: e5-small

| Model | First index | Vectors on disk | MRR, hybrid | MRR, + reranker | R@3, + reranker |
| --- | --- | --- | --- | --- | --- |
| multilingual-e5-small (int8, 118 MB) | 6 min 4 s | 5 MB | 0.755 | 0.783 | 84% |
| multilingual-e5-base (int8, 279 MB) | 14 min 26 s¹ | 9 MB | 0.719 | 0.779 | 87% |

¹ Measured while other runs used the CPU, so the ratio is approximate.

e5-base is not better on this set: lower without the reranker, equal with
it, and +3 points of recall@3 (2 queries, within noise). Its model file is
2.4 times larger (279 MB against 118 MB) and indexing took ≈ 2.4 times
longer. Kept: e5-small. bge-m3 (568 M parameters) was not
tested: it alone would exceed the 600 MB memory budget on an 8 GB Mac.

### Meaning-only results: cut far below the best

A file found only by meaning, with a cosine more than 0.03 below the best
match, is dropped. On this set it changes no metric (MRR 0.755 with margins
0, 0.02, 0.03 and 0.05), and it removes the unrelated results that filled
the end of the list ("gratin dauphinois" for "devis cuisine").

## Remaining misses

10 of 61 queries miss the top 3. Four have no fix in this design: two expect
iCloud placeholders whose names share no word with the query (an
abbreviation such as `RDD` for "régression sur discontinuité"), and two are
French queries for English documents with generic words. Two find a
near-equivalent first: another file on the same notes in the same folder,
and another version of the same presentation.

## Memory

| Component | Resident memory |
| --- | --- |
| Python, numpy, tantivy, server | ≈ 70 MB |
| e5-small (ONNX Runtime, int8) | ≈ 270 MB |
| XLM-RoBERTa vocabulary (sentencepiece) | ≈ 65 MB |
| Reranker (ONNX Runtime, int8) | ≈ 135 MB |
| **Server, warm, reranker on** | **≈ 575 MB** |

The vocabulary was first loaded with the Hugging Face `tokenizers` library:
≈ 390 MB for the same 250 002 entries, and a second copy for the reranker.
Reading the original sentencepiece model gives the same ids (2 differences in
11 test texts, on ties in repeated characters) for ≈ 65 MB, shared by both
models.

## Indexing time

| Step | Time |
| --- | --- |
| Walk and metadata, 4 408 files | 0.9 s |
| Names and folders searchable | 1.2 s |
| Content and vectors, 950 local files | ≈ 5 min |
| Total, first run | 6 min 4 s |
| Change picked up by the watcher | 2.3 to 2.7 s |

Vectors are computed for the first 16 chunks (≈ 4 000 tokens) of each file;
the rest of a long text stays searchable by keywords. With 48 chunks, large
local files went through at ≈ 1 file/s instead of ≈ 2.5 file/s. Indexing runs at utility
priority when you start it, at background priority when the watcher does.
