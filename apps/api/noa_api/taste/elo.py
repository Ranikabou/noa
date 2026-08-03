"""Pairwise Elo — calibrating the scorer from A/B judgements.

People are unreliable at absolute rating (1–10) and very reliable at A/B. So we
never ask for a score; we collect "A beats B" comparisons over our own generated
output and let an Elo update distil them into a ranking. Fifty comparisons a week
is enough to keep the scorer calibrated.

The ratings this produces are the ground truth the manifold scorer is fit and
sanity-checked against: if the scorer's ordering disagrees with the Elo ordering
on held-out pairs, the scorer — not the human — is wrong.

Deterministic and stdlib-only. Comparisons are applied in the order given, so the
same log yields the same ratings (important for reproducibility and for resuming a
calibration run).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

DEFAULT_RATING = 1000.0
DEFAULT_K = 32.0


@dataclass(frozen=True)
class PairwiseComparison:
    """A single A/B judgement: ``winner`` was preferred over ``loser``.

    ``weight`` lets a confident, expensive judgement count for more than a quick
    one without inventing a rating scale.
    """

    winner: str
    loser: str
    weight: float = 1.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability A beats B under the logistic Elo model, in ``(0, 1)``."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def compute_elo(
    items: Iterable[str],
    comparisons: Iterable[PairwiseComparison],
    k: float = DEFAULT_K,
    base_rating: float = DEFAULT_RATING,
) -> dict:
    """Fold an ordered stream of comparisons into a ``{item: rating}`` map.

    Every item in ``items`` starts at ``base_rating``; items that appear only in
    ``comparisons`` are seeded lazily at ``base_rating`` too, so the caller need
    not enumerate them up front.
    """
    ratings: dict = {item: base_rating for item in items}

    for cmp in comparisons:
        ra = ratings.setdefault(cmp.winner, base_rating)
        rb = ratings.setdefault(cmp.loser, base_rating)
        exp_win = expected_score(ra, rb)
        delta = k * cmp.weight * (1.0 - exp_win)
        ratings[cmp.winner] = ra + delta
        ratings[cmp.loser] = rb - delta

    return ratings


def rank_by_elo(ratings: dict) -> list:
    """Items ordered best-first. Ties broken by id for stable output."""
    return [item for item, _ in sorted(ratings.items(), key=lambda kv: (-kv[1], kv[0]))]
