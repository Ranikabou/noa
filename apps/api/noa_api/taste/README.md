# Taste — a rejection function

> Taste is a *rejection* function, not a generation function. Models are trained to
> produce the conditional average, and the average is exactly what taste is defined
> against. So you don't prompt taste in — you build a filter that kills almost
> everything.

This package is that filter for NOA's render pipeline. The generator
(render-worker) overgenerates candidate images; this module decides which few
survive. It is pure stdlib (`math`, `dataclasses`) — no numpy, DB, S3, or CLIP —
so the entire taste boundary is unit-testable in isolation
(`apps/api/tests/test_taste_rejection.py`, 30 tests).

## The five principles, mapped to code

| Principle | Where |
|---|---|
| **Overgenerate, then be brutal.** Selectivity ratio *is* the taste — generate 100, ship 3. | `TasteRejectionFunction.select(..., keep=k)` → `Selection.selectivity` |
| **The reference corpus is the taste.** Score by local distance to a tight canon, not a general prior. | `manifold.knn_affinity` (k-NN, not centroid) |
| **Collect rejections, not just exemplars.** Near-misses carry the signal; the score is contrastive. | `manifold.manifold_score` = canon affinity − rejection affinity |
| **Label by pairwise comparison, never 1–10.** Distil A/B judgements into ratings. | `elo.compute_elo` / `PairwiseComparison` |
| **Constrain hard and stay constrained.** Fixed palette, crop grammar, refused list — any violation disqualifies. | `constraints.HardConstraints` |

The via-negativa framing is the honest one: you can't specify what makes an image
good, but you can accumulate a long list of what disqualifies it, and *that* list
transfers to a machine in a way positive description doesn't. `HardConstraints`
returns named disqualifiers; no manifold score ever overrides one.

## Shape

```
manifold.py     cosine / k-NN affinity / contrastive manifold_score
constraints.py  refused motifs, fixed Palette, crop grammar → disqualifiers
elo.py          pairwise A/B → ratings that calibrate the scorer
rejection.py    Candidate → Verdict; batch → Selection (overgenerate-then-cut)
adapter.py      NOA rows (InspirationItem / StyleProfile / RenderImage) → the above
```

## How it reads NOA's data

The boundary is assembled from data the product already collects:

- **`InspirationItem.sentiment`** splits a board into the two corpora — `positive`
  items are the canon, `negative` items are the near-miss rejection set.
- **`StyleProfile.style_signals.negative_preferences`** becomes the refused-motif
  list; **`material_palette[].color_hex`** becomes the fixed palette.
- A **`RenderImage`** (plus tags/colours the render step attaches) becomes a
  `Candidate`.

`adapter.build_config(...)` wires all of that into a `TasteConfig` in one call.

## Usage

```python
from noa_api.taste import build_config, candidate_from_render, TasteRejectionFunction

cfg = build_config(inspiration_items, style_profile, keep=3)   # ship 3
trf = TasteRejectionFunction(cfg)

candidates = [candidate_from_render(r, extra) for r, extra in render_rows]
selection = trf.select(candidates)          # overgenerate 100 → keep 3

selection.kept           # survivors, best-first
selection.selectivity    # 0.03 — the taste
selection.rejected       # every reject, with its reasons (refused_motif / off_palette / below_cut ...)
```

## Embeddings — the space the manifold lives in

The manifold only means anything once images are vectors in one shared, semantic
space. That space is `noa_api.embeddings`:

- **`clip-vit-l-14`** (real CLIP, 768-dim) when `open_clip_torch` + `torch` are
  installed (`pip install -e "apps/api[clip]"`). This is the semantic embedding
  that gives the manifold actual taste.
- **`hash-fallback`** — a deterministic, dependency-free vector used in dev/CI so
  the pipeline runs without torch. It has geometry but **no meaning**; it proves
  the wiring, it is not taste. `taste.corpus_is_semantic(items)` reports which one
  a corpus carries.

`style_inference` embeds every inspiration item and stores it on
`inspiration_items.embedding` (canon = positive items, rejections = negative
items); the style profile's `embedding_vector` is the positive-exemplar centroid,
not the old zero vector. Render candidates share the identical provider, so
corpus and candidates are always comparable.

## Where it plugs in

This is the discriminator half of the **critic-worker** (`services/critic-worker`).
The critic already scores plan fidelity and geometric consistency; the taste
function adds the aesthetic cut, feeding `CritiqueReport.scores.inspiration_alignment`
and `render_coherence` and gating which renders reach the user. One call does it:

```python
from noa_api.taste import filter_render_batch

selection = filter_render_batch(inspiration_items, style_profile, render_candidates, keep=3)
```

The only thing still stubbed upstream is the render-worker itself: once it produces
candidates (and embeds them via `noa_api.embeddings`), this filter cuts them with
no further wiring.
