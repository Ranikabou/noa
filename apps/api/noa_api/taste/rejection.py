"""The taste rejection function.

Overgenerate, then be brutal. The generator ships many candidates; this function
keeps a few. It composes the two halves of taste:

- **Refusal (hard).** ``HardConstraints`` disqualify a candidate outright — a
  refused motif, an off-palette colour story, a broken crop. No score overrides a
  disqualifier.
- **Manifold (soft).** Among the survivors, rank by contrastive distance to the
  canon minus the near-miss rejection set, then cut to ``keep``.

The selectivity ratio (kept / seen) *is* the taste. A filter that keeps 40% of
what the generator hands it has no taste; one that keeps 3% might. ``Selection``
surfaces that ratio and every rejection reason, because the rejections — not the
survivors — are what you inspect to see whether the boundary sits where you meant
it to.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from .constraints import HardConstraints
from .manifold import manifold_score


@dataclass(frozen=True)
class Candidate:
    """One render candidate presented to the filter.

    Everything is optional so partial candidates degrade gracefully: a candidate
    with no embedding simply scores 0 on the manifold; one with no tags/colours
    can only be rejected by the checks that do apply to it.
    """

    id: str
    embedding: Sequence[float] | None = None
    tags: Sequence[str] = ()
    colors: Sequence[str] = ()
    aspect_ratio: float | None = None


@dataclass(frozen=True)
class Verdict:
    """The filter's judgement on a single candidate."""

    candidate_id: str
    accepted: bool
    score: float
    disqualifiers: list = field(default_factory=list)
    reasons: list = field(default_factory=list)

    @property
    def disqualified(self) -> bool:
        """True if a hard constraint fired (distinct from losing the score cut)."""
        return bool(self.disqualifiers)


@dataclass(frozen=True)
class Selection:
    """The outcome of filtering a batch: the survivors and why the rest died."""

    kept: list  # list[Verdict], accepted, best-first
    rejected: list  # list[Verdict], rejected, worst offenders first
    seen: int

    @property
    def selectivity(self) -> float:
        """Kept / seen — the taste. Lower is more selective. 0.0 for an empty batch."""
        return len(self.kept) / self.seen if self.seen else 0.0


@dataclass(frozen=True)
class TasteConfig:
    """Everything the filter needs: the canon, the boundary, and the refusals.

    ``exemplars`` and ``rejections`` are embedding corpora (the loved set and the
    near-miss set). ``constraints`` is the refused list / palette / crop grammar.
    ``keep`` and ``keep_ratio`` set how brutal the cut is; give one or neither
    (``keep`` wins if both are set). With neither, every non-disqualified
    candidate survives — useful for scoring-only passes.
    """

    exemplars: Sequence[Sequence[float]] = ()
    rejections: Sequence[Sequence[float]] = ()
    constraints: HardConstraints = field(default_factory=HardConstraints)
    k: int = 5
    rejection_weight: float = 1.0
    #: Absolute manifold-score floor; survivors must also clear this if set.
    min_score: float | None = None
    #: Keep at most this many after ranking (overgenerate-then-be-brutal).
    keep: int | None = None
    #: Or keep this fraction of the batch (ceil). Ignored when ``keep`` is set.
    keep_ratio: float | None = None


class TasteRejectionFunction:
    """A configured filter. Reusable across batches; holds no per-batch state."""

    def __init__(self, config: TasteConfig):
        self.config = config

    def score(self, candidate: Candidate) -> float:
        """Contrastive manifold score for a candidate (0.0 without an embedding)."""
        if not candidate.embedding:
            return 0.0
        return manifold_score(
            candidate.embedding,
            self.config.exemplars,
            self.config.rejections,
            k=self.config.k,
            rejection_weight=self.config.rejection_weight,
        )

    def evaluate(self, candidate: Candidate) -> Verdict:
        """Judge one candidate against constraints and the score floor.

        This does *not* apply the top-``keep`` cut — that is a batch-relative
        decision made in :meth:`select`. Here a candidate is accepted iff it trips
        no hard constraint and clears ``min_score``.
        """
        disqualifiers = self.config.constraints.disqualifiers(
            tags=candidate.tags,
            colors=candidate.colors,
            aspect_ratio=candidate.aspect_ratio,
        )
        score = self.score(candidate)
        reasons: list = list(disqualifiers)

        accepted = not disqualifiers
        if accepted and self.config.min_score is not None and score < self.config.min_score:
            accepted = False
            reasons.append(f"below_min_score:{score:.4f}<{self.config.min_score:.4f}")

        return Verdict(
            candidate_id=candidate.id,
            accepted=accepted,
            score=score,
            disqualifiers=disqualifiers,
            reasons=reasons,
        )

    def select(
        self,
        candidates: Sequence[Candidate],
        keep: int | None = None,
        keep_ratio: float | None = None,
    ) -> Selection:
        """Overgenerate-then-be-brutal: evaluate all, rank survivors, cut to keep.

        Per-call ``keep`` / ``keep_ratio`` override the config. Disqualified and
        below-floor candidates never enter the ranking; among those that pass,
        the highest scores survive up to the cut and the rest are rejected with a
        ``below_cut`` reason, so every rejection is explainable.
        """
        verdicts = [self.evaluate(c) for c in candidates]
        passing = [v for v in verdicts if v.accepted]
        failing = [v for v in verdicts if not v.accepted]

        # Best-first among those that cleared constraints and the floor.
        passing.sort(key=lambda v: (-v.score, v.candidate_id))

        cut = self._resolve_cut(len(passing), keep, keep_ratio)

        kept = passing[:cut]
        cut_losers = passing[cut:]

        # Mark the ones that passed constraints but lost the score cut.
        demoted = [
            Verdict(
                candidate_id=v.candidate_id,
                accepted=False,
                score=v.score,
                disqualifiers=v.disqualifiers,
                reasons=v.reasons + ["below_cut"],
            )
            for v in cut_losers
        ]

        # Rejected list: hard failures first (most severe), then score-cut losers,
        # each group ordered worst-scoring first for quick eyeballing of the edge.
        failing.sort(key=lambda v: (v.score, v.candidate_id))
        rejected = failing + demoted

        return Selection(kept=kept, rejected=rejected, seen=len(candidates))

    def _resolve_cut(
        self, n_passing: int, keep: int | None, keep_ratio: int | None
    ) -> int:
        if keep is None:
            keep = self.config.keep
        if keep_ratio is None:
            keep_ratio = self.config.keep_ratio

        if keep is not None:
            return max(0, min(keep, n_passing))
        if keep_ratio is not None:
            return max(0, min(math.ceil(keep_ratio * n_passing), n_passing))
        return n_passing
