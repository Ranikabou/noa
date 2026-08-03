"""Mapping NOA's domain records into the taste filter's vocabulary.

The filter is deliberately domain-agnostic (embeddings, tags, colours). This
module is the thin, pure translation layer that reads it out of what NOA already
stores, so the taste boundary is assembled from data the product collects anyway:

- ``InspirationItem.sentiment`` splits the board into the two corpora the filter
  needs. Positive items are the canon; negative items ("90% right and I hate it")
  are the near-miss rejection set. Collecting rejections, not just exemplars, is
  what makes the boundary sharp — so the negative items are first-class here.
- ``StyleProfile.negative_preferences`` becomes the refused-motif list, and the
  ``material_palette`` colours become the fixed palette. Both are the *refusal*
  half of taste, lifted straight out of the inferred style.
- A ``RenderImage`` (plus whatever tags/colours the render-worker attaches)
  becomes a :class:`Candidate`.

Everything here takes plain dicts shaped like the DB rows / contracts, so it runs
without a database, S3, or CLIP — the same reason the rest of the package is pure
stdlib. Wiring it to the ARQ worker is a matter of passing real rows in.
"""
from __future__ import annotations

from typing import Any, Sequence

from .constraints import HardConstraints, Palette
from .rejection import Candidate, TasteConfig


def split_corpus(items: Sequence[dict]) -> tuple[list, list]:
    """Split inspiration items into (exemplar_embeddings, rejection_embeddings).

    Items without an embedding are skipped — a corpus vector with no vector is no
    signal. Sentiment defaults to positive when absent, matching the contract's
    ``"positive" | "negative"`` field.
    """
    exemplars: list = []
    rejections: list = []
    for item in items:
        emb = item.get("embedding")
        if not emb:
            continue
        if item.get("sentiment", "positive") == "negative":
            rejections.append(emb)
        else:
            exemplars.append(emb)
    return exemplars, rejections


def constraints_from_style_profile(
    style_profile: dict | None,
    palette_tolerance: float = 0.12,
    max_off_palette_fraction: float = 0.15,
    allowed_aspect_ratios: Sequence[float] = (),
) -> HardConstraints:
    """Build the refused list + palette from a ``StyleProfile.style_signals``.

    Pulls ``negative_preferences`` into the refused-motif list and every
    ``material_palette[].color_hex`` into the fixed palette. A missing profile (or
    missing signals) yields empty, permissive constraints rather than raising.
    """
    if not style_profile:
        return HardConstraints(allowed_aspect_ratios=allowed_aspect_ratios)

    signals = style_profile.get("style_signals", style_profile) or {}

    refused = {
        str(p).strip().lower()
        for p in signals.get("negative_preferences", [])
        if str(p).strip()
    }

    swatches = [
        entry["color_hex"]
        for entry in signals.get("material_palette", [])
        if isinstance(entry, dict) and entry.get("color_hex")
    ]
    palette = (
        Palette(
            swatches=swatches,
            tolerance=palette_tolerance,
            max_off_palette_fraction=max_off_palette_fraction,
        )
        if swatches
        else None
    )

    return HardConstraints(
        refused_motifs=frozenset(refused),
        palette=palette,
        allowed_aspect_ratios=allowed_aspect_ratios,
    )


def build_config(
    inspiration_items: Sequence[dict],
    style_profile: dict | None = None,
    *,
    k: int = 5,
    rejection_weight: float = 1.0,
    min_score: float | None = None,
    keep: int | None = None,
    keep_ratio: float | None = None,
    allowed_aspect_ratios: Sequence[float] = (),
) -> TasteConfig:
    """Assemble a full :class:`TasteConfig` from a board + its style profile."""
    exemplars, rejections = split_corpus(inspiration_items)
    constraints = constraints_from_style_profile(
        style_profile, allowed_aspect_ratios=allowed_aspect_ratios
    )
    return TasteConfig(
        exemplars=exemplars,
        rejections=rejections,
        constraints=constraints,
        k=k,
        rejection_weight=rejection_weight,
        min_score=min_score,
        keep=keep,
        keep_ratio=keep_ratio,
    )


def candidate_from_render(render_image: dict, extra: dict | None = None) -> Candidate:
    """Map a ``RenderImage`` row (+ render-worker extras) to a :class:`Candidate`.

    ``render_image`` supplies id and, if present, a computed embedding and
    resolution (for the crop grammar). ``extra`` carries anything the render step
    tags on that isn't in the stored contract — detected motifs, dominant colours
    — keeping the contract clean while still feeding the filter.
    """
    extra = extra or {}

    aspect_ratio = extra.get("aspect_ratio")
    if aspect_ratio is None:
        res = render_image.get("resolution") or {}
        w, h = res.get("width"), res.get("height")
        if w and h:
            aspect_ratio = w / h

    return Candidate(
        id=str(render_image.get("id")),
        embedding=extra.get("embedding") or render_image.get("embedding"),
        tags=extra.get("tags", ()),
        colors=extra.get("colors", ()),
        aspect_ratio=aspect_ratio,
    )


def as_dict(obj: Any) -> dict:
    """Best-effort coercion of a Verdict/Selection to a JSON-serialisable dict.

    Handy at the API boundary (e.g. attaching a taste report to a job event)
    without importing the dataclasses there.
    """
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    raise TypeError(f"cannot coerce {type(obj)!r} to dict")
