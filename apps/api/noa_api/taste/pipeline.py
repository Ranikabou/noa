"""End-to-end glue: board + style profile + render candidates → a Selection.

This is the single call the render/critic worker makes to apply taste to a batch
of freshly-rendered candidates. It assembles the filter from the board's stored
data and runs the overgenerate-then-be-brutal cut, so the worker never touches the
manifold internals.

**Embedding-space invariant.** Distances are only meaningful when the corpus
(inspiration items) and the candidates were embedded by the *same* model. Both
sides go through :mod:`noa_api.embeddings`, which is process-global, so a single
deployment is automatically consistent. ``embedding_model`` is stored on every
row for provenance and future cross-model guards; :func:`corpus_is_semantic`
reports whether the corpus carries real CLIP vectors or only the dev hash
fallback, so a caller can refuse to trust a purely-mechanical cut.
"""
from __future__ import annotations

from typing import Sequence

from .adapter import build_config, candidate_from_render
from .rejection import Selection, TasteRejectionFunction


def corpus_is_semantic(inspiration_items: Sequence[dict]) -> bool:
    """True when at least one embedded item was produced by a real CLIP model.

    A corpus embedded only by the ``hash-fallback`` backend has geometry but no
    meaning, so a taste cut over it is plumbing, not judgement — worth surfacing.
    """
    return any(
        item.get("embedding") and item.get("embedding_model", "").startswith("clip")
        for item in inspiration_items
    )


def filter_render_batch(
    inspiration_items: Sequence[dict],
    style_profile: dict | None,
    render_candidates: Sequence[dict],
    *,
    keep: int | None = None,
    keep_ratio: float | None = None,
    extras: dict | None = None,
    allowed_aspect_ratios: Sequence[float] = (),
) -> Selection:
    """Apply the taste filter to a batch of render candidates.

    ``inspiration_items`` are board rows (each with ``embedding``/``sentiment``);
    ``style_profile`` supplies the refused list and palette; ``render_candidates``
    are ``render_outputs`` rows (each with ``embedding`` and ``resolution``).
    ``extras`` maps a candidate id → extra signals the render step computed but
    didn't store (detected tags, dominant colours). Returns the :class:`Selection`
    — survivors, rejects with reasons, and the selectivity ratio.
    """
    cfg = build_config(
        inspiration_items,
        style_profile,
        keep=keep,
        keep_ratio=keep_ratio,
        allowed_aspect_ratios=allowed_aspect_ratios,
    )
    trf = TasteRejectionFunction(cfg)

    extras = extras or {}
    candidates = [
        candidate_from_render(row, extras.get(str(row.get("id"))))
        for row in render_candidates
    ]
    return trf.select(candidates)
