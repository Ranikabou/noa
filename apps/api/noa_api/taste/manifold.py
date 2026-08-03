"""Distance to the taste manifold.

The reference corpus *is* the taste: a tight, personally chosen set of a few
hundred embeddings, not a broad "good interiors" prior. We score a candidate by
how close it sits to that manifold locally — the mean similarity to its k nearest
exemplars — rather than to the corpus centroid, which would collapse a canon with
internal variety into a bland average (exactly the conditional average taste is
defined against).

The score is *contrastive*. We keep two corpora: exemplars (things loved) and
rejections (near-misses — "90% right and I hate it"). A candidate's taste score is
its affinity to the canon minus its affinity to the rejection set. Near-misses
carry almost all the signal about where the boundary sits, so subtracting them is
what makes the filter sharp rather than merely agreeable.

Pure stdlib (``math`` only): no numpy dependency, so the scorer is trivially
unit-testable and cheap to run per candidate.
"""
from __future__ import annotations

import math
from typing import Sequence

Vector = Sequence[float]


def cosine_similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity in ``[-1, 1]``.

    Returns 0.0 when either vector is empty, a zero vector, or of mismatched
    length — degenerate inputs contribute no signal rather than raising, so a
    single malformed embedding cannot sink a whole batch.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def knn_affinity(vec: Vector, corpus: Sequence[Vector], k: int = 5) -> float:
    """Mean cosine similarity to the ``k`` nearest members of ``corpus``.

    This is a *local* measure of manifold proximity: a candidate that lands near
    one dense pocket of the canon scores well even if it is far from the rest of
    it. Using the whole corpus (or its centroid) instead would reward blandness.

    Returns 0.0 for an empty corpus. ``k`` is clamped to the corpus size, so a
    corpus smaller than ``k`` simply averages over all of it.
    """
    if not corpus:
        return 0.0
    k = max(1, min(k, len(corpus)))
    sims = sorted((cosine_similarity(vec, ref) for ref in corpus), reverse=True)
    top = sims[:k]
    return sum(top) / len(top)


def manifold_score(
    vec: Vector,
    exemplars: Sequence[Vector],
    rejections: Sequence[Vector] = (),
    k: int = 5,
    rejection_weight: float = 1.0,
) -> float:
    """Contrastive taste score: canon affinity minus rejection affinity.

    ``rejection_weight`` scales how hard the near-miss corpus pushes back. At 1.0
    a candidate sitting exactly between a loved exemplar and a hated near-miss
    scores ~0; raise it to make the boundary less forgiving on the reject side.

    With no rejection corpus this reduces to plain k-NN affinity to the canon.
    The result is unbounded below but bounded above by 1.0 (perfect canon match,
    no rejection pull).
    """
    canon = knn_affinity(vec, exemplars, k)
    if not rejections:
        return canon
    reject = knn_affinity(vec, rejections, k)
    return canon - rejection_weight * reject
