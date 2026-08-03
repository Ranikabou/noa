"""Taste as a rejection function.

Taste is a *rejection* function, not a generation function. A generator produces
the conditional average; the average is exactly what taste is defined against.
So we don't prompt taste in — we build a filter that kills almost everything and
keeps only the few candidates that survive.

This package implements that filter for NOA's render pipeline. The generator
(render-worker) overgenerates candidate images; this module scores them against a
tight, personally chosen reference corpus and a densely-sampled boundary of
rejections, applies hard constraints, and keeps a small fraction.

Principles, each mapped to code:

- **Overgenerate, then be brutal.** ``TasteRejectionFunction.select`` takes N
  candidates and returns a small ``keep`` — the selectivity ratio *is* the taste.
- **The reference corpus is the taste.** ``manifold`` scores by local distance to
  a small canon (k-NN affinity), not to a general aesthetic prior.
- **Collect rejections, not just exemplars.** The score is contrastive: affinity
  to the canon *minus* affinity to the near-miss rejection set. Near-misses carry
  most of the signal, so the boundary is where we sample densest.
- **Label by pairwise comparison, never 1–10.** ``elo`` distils A/B judgements
  into ratings that calibrate the scorer.
- **Constrain hard and stay constrained.** ``constraints`` encodes a fixed
  palette, a crop grammar, and a refused list — any one violation disqualifies a
  candidate outright, regardless of how well it scores.
"""
from __future__ import annotations

from .adapter import (
    build_config,
    candidate_from_render,
    constraints_from_style_profile,
    split_corpus,
)
from .constraints import HardConstraints, Palette
from .elo import PairwiseComparison, compute_elo, expected_score, rank_by_elo
from .manifold import cosine_similarity, knn_affinity, manifold_score
from .pipeline import corpus_is_semantic, filter_render_batch
from .rejection import (
    Candidate,
    Selection,
    TasteConfig,
    TasteRejectionFunction,
    Verdict,
)

__all__ = [
    "Candidate",
    "HardConstraints",
    "Palette",
    "PairwiseComparison",
    "Selection",
    "TasteConfig",
    "TasteRejectionFunction",
    "Verdict",
    "build_config",
    "candidate_from_render",
    "compute_elo",
    "constraints_from_style_profile",
    "corpus_is_semantic",
    "cosine_similarity",
    "expected_score",
    "filter_render_batch",
    "knn_affinity",
    "manifold_score",
    "rank_by_elo",
    "split_corpus",
]
