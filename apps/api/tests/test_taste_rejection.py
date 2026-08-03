"""Taste rejection function: manifold, constraints, Elo, and selection.

Pure-stdlib tests — no DB, S3, CLIP, or numpy — mirroring the module itself, so
the whole taste boundary is verifiable in isolation.
"""
import math

import pytest

from noa_api.taste import (
    Candidate,
    HardConstraints,
    Palette,
    PairwiseComparison,
    TasteConfig,
    TasteRejectionFunction,
    build_config,
    candidate_from_render,
    compute_elo,
    constraints_from_style_profile,
    cosine_similarity,
    expected_score,
    knn_affinity,
    manifold_score,
    rank_by_elo,
    split_corpus,
)
from noa_api.taste.constraints import color_distance, hex_to_rgb

# --------------------------------------------------------------------------- #
# manifold
# --------------------------------------------------------------------------- #


def test_cosine_identity_and_orthogonality():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_degenerate_inputs_return_zero():
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0  # length mismatch


def test_knn_affinity_is_local_not_centroid():
    # One tight pocket near [1,0], one far cluster near [0,1].
    corpus = [[1.0, 0.0], [0.98, 0.02], [0.0, 1.0], [0.02, 0.98]]
    near_pocket = knn_affinity([1.0, 0.0], corpus, k=2)
    # k=2 averages only the two nearest (the pocket), so affinity stays high;
    # a centroid measure would be dragged toward 0.5 by the far cluster.
    assert near_pocket > 0.99


def test_knn_affinity_empty_corpus():
    assert knn_affinity([1.0, 0.0], [], k=5) == 0.0


def test_manifold_score_is_contrastive():
    exemplars = [[1.0, 0.0]]
    rejections = [[0.0, 1.0]]
    # Sits on the canon → high; sits on a rejection → negative.
    assert manifold_score([1.0, 0.0], exemplars, rejections) == pytest.approx(1.0)
    assert manifold_score([0.0, 1.0], exemplars, rejections) == pytest.approx(-1.0)
    # Halfway between: canon pull and rejection push cancel to ~0.
    assert manifold_score([1.0, 1.0], exemplars, rejections) == pytest.approx(0.0, abs=1e-9)


def test_rejection_weight_sharpens_boundary():
    exemplars = [[1.0, 0.0]]
    rejections = [[0.9, 0.1]]  # a near-miss: close to the canon but hated
    soft = manifold_score([0.95, 0.05], exemplars, rejections, rejection_weight=1.0)
    hard = manifold_score([0.95, 0.05], exemplars, rejections, rejection_weight=3.0)
    assert hard < soft  # heavier rejection weight pushes the near-miss down


# --------------------------------------------------------------------------- #
# constraints
# --------------------------------------------------------------------------- #


def test_hex_parsing_variants():
    assert hex_to_rgb("#ffffff") == (255, 255, 255)
    assert hex_to_rgb("000000") == (0, 0, 0)
    assert hex_to_rgb("#fff") == (255, 255, 255)
    with pytest.raises(ValueError):
        hex_to_rgb("#12")


def test_color_distance_bounds():
    assert color_distance("#000000", "#000000") == pytest.approx(0.0)
    assert color_distance("#000000", "#ffffff") == pytest.approx(1.0)


def test_refused_motifs_disqualify_case_insensitively():
    c = HardConstraints(refused_motifs=frozenset({"neon", "industrial pipes"}))
    reasons = c.disqualifiers(tags=["Cozy", "NEON", "wood"])
    assert reasons == ["refused_motif:neon"]


def test_palette_tolerates_small_accent_but_rejects_drift():
    palette = Palette(swatches=["#efe7d8", "#3b3a36"], tolerance=0.1, max_off_palette_fraction=0.34)
    c = HardConstraints(palette=palette)
    # 1 of 3 off-palette (33%) is within the accent budget → admissible.
    assert c.disqualifiers(colors=["#efe7d8", "#3b3a36", "#ff0000"]) == []
    # 2 of 3 off-palette (66%) → the colour story has wandered → disqualified.
    dq = c.disqualifiers(colors=["#efe7d8", "#ff0000", "#00ff00"])
    assert any(r.startswith("off_palette") for r in dq)


def test_crop_grammar():
    c = HardConstraints(allowed_aspect_ratios=[1.5, 1.0], aspect_ratio_tolerance=0.05)
    assert c.disqualifiers(aspect_ratio=1.5) == []
    assert c.disqualifiers(aspect_ratio=1.02) == []  # within 5% of 1.0
    assert c.disqualifiers(aspect_ratio=1.78) == ["bad_crop:1.780"]


def test_no_constraints_admits_everything():
    c = HardConstraints()
    assert c.disqualifiers(tags=["anything"], colors=["#123456"], aspect_ratio=2.35) == []


# --------------------------------------------------------------------------- #
# elo
# --------------------------------------------------------------------------- #


def test_expected_score_symmetry():
    assert expected_score(1000, 1000) == pytest.approx(0.5)
    assert expected_score(1200, 1000) > 0.5
    assert expected_score(1000, 1200) == pytest.approx(1 - expected_score(1200, 1000))


def test_elo_orders_by_wins():
    comparisons = [
        PairwiseComparison("a", "b"),
        PairwiseComparison("a", "c"),
        PairwiseComparison("b", "c"),
    ]
    ratings = compute_elo(["a", "b", "c"], comparisons)
    assert rank_by_elo(ratings) == ["a", "b", "c"]
    assert ratings["a"] > ratings["b"] > ratings["c"]


def test_elo_seeds_unseen_items_lazily():
    ratings = compute_elo([], [PairwiseComparison("x", "y")])
    assert ratings["x"] > 1000.0 > ratings["y"]


def test_elo_is_deterministic():
    cmps = [PairwiseComparison("a", "b"), PairwiseComparison("b", "a")]
    assert compute_elo(["a", "b"], cmps) == compute_elo(["a", "b"], cmps)


def test_elo_weight_amplifies_update():
    light = compute_elo(["a", "b"], [PairwiseComparison("a", "b", weight=1.0)])
    heavy = compute_elo(["a", "b"], [PairwiseComparison("a", "b", weight=3.0)])
    assert heavy["a"] > light["a"]


# --------------------------------------------------------------------------- #
# rejection function
# --------------------------------------------------------------------------- #


def _basic_config(**overrides):
    cfg = dict(
        exemplars=[[1.0, 0.0]],
        rejections=[[0.0, 1.0]],
        constraints=HardConstraints(refused_motifs=frozenset({"neon"})),
    )
    cfg.update(overrides)
    return TasteConfig(**cfg)


def test_hard_constraint_overrides_a_perfect_score():
    trf = TasteRejectionFunction(_basic_config())
    # Perfect manifold match, but carries a refused motif → rejected outright.
    v = trf.evaluate(Candidate("x", embedding=[1.0, 0.0], tags=["neon"]))
    assert not v.accepted
    assert v.disqualified
    assert v.score == pytest.approx(1.0)  # score still computed, just overridden
    assert v.disqualifiers == ["refused_motif:neon"]


def test_min_score_floor_rejects_low_manifold():
    trf = TasteRejectionFunction(_basic_config(min_score=0.5))
    v = trf.evaluate(Candidate("x", embedding=[0.0, 1.0]))  # sits on a rejection
    assert not v.accepted
    assert not v.disqualified  # not a hard constraint — it's the score floor
    assert any(r.startswith("below_min_score") for r in v.reasons)


def test_candidate_without_embedding_scores_zero():
    trf = TasteRejectionFunction(_basic_config())
    assert trf.score(Candidate("x")) == 0.0


def test_select_is_brutal_and_ranked():
    trf = TasteRejectionFunction(_basic_config())
    candidates = [
        Candidate("good", embedding=[1.0, 0.0]),        # on canon
        Candidate("mid", embedding=[0.7, 0.7]),         # between
        Candidate("bad", embedding=[0.0, 1.0]),         # on rejection
        Candidate("refused", embedding=[1.0, 0.0], tags=["neon"]),  # disqualified
    ]
    sel = trf.select(candidates, keep=1)

    assert [v.candidate_id for v in sel.kept] == ["good"]
    assert sel.seen == 4
    assert sel.selectivity == pytest.approx(0.25)

    # Disqualified candidate is rejected regardless of its perfect score.
    refused = next(v for v in sel.rejected if v.candidate_id == "refused")
    assert refused.disqualified
    # A passing-but-cut candidate is rejected with an explicit below_cut reason.
    mid = next(v for v in sel.rejected if v.candidate_id == "mid")
    assert "below_cut" in mid.reasons
    assert not mid.disqualified


def test_keep_ratio_ceils():
    trf = TasteRejectionFunction(_basic_config())
    cands = [Candidate(str(i), embedding=[1.0, 0.0]) for i in range(10)]
    sel = trf.select(cands, keep_ratio=0.25)
    assert len(sel.kept) == 3  # ceil(0.25 * 10)


def test_select_empty_batch():
    trf = TasteRejectionFunction(_basic_config())
    sel = trf.select([])
    assert sel.kept == []
    assert sel.selectivity == 0.0


def test_per_call_keep_overrides_config():
    trf = TasteRejectionFunction(_basic_config(keep=1))
    cands = [Candidate(str(i), embedding=[1.0, 0.0]) for i in range(5)]
    assert len(trf.select(cands).kept) == 1          # config default
    assert len(trf.select(cands, keep=3).kept) == 3  # per-call override


# --------------------------------------------------------------------------- #
# adapter
# --------------------------------------------------------------------------- #


def test_split_corpus_by_sentiment_skipping_embeddingless():
    items = [
        {"embedding": [1.0, 0.0], "sentiment": "positive"},
        {"embedding": [0.0, 1.0], "sentiment": "negative"},
        {"embedding": None, "sentiment": "positive"},   # skipped
        {"sentiment": "positive"},                        # skipped
        {"embedding": [0.5, 0.5]},                         # defaults positive
    ]
    exemplars, rejections = split_corpus(items)
    assert exemplars == [[1.0, 0.0], [0.5, 0.5]]
    assert rejections == [[0.0, 1.0]]


def test_constraints_from_style_profile():
    profile = {
        "style_signals": {
            "negative_preferences": ["Neon colors", "industrial pipes"],
            "material_palette": [
                {"name": "oak", "color_hex": "#c9a66b"},
                {"name": "plaster", "color_hex": "#efe7d8"},
                {"name": "no-color-entry"},  # ignored
            ],
        }
    }
    c = constraints_from_style_profile(profile)
    assert "neon colors" in c.refused_motifs
    assert c.palette is not None
    assert c.palette.swatches == ["#c9a66b", "#efe7d8"]


def test_constraints_from_missing_profile_is_permissive():
    c = constraints_from_style_profile(None)
    assert c.disqualifiers(tags=["neon"], colors=["#ff0000"]) == []


def test_build_config_end_to_end():
    items = [
        {"embedding": [1.0, 0.0], "sentiment": "positive"},
        {"embedding": [0.0, 1.0], "sentiment": "negative"},
    ]
    profile = {"style_signals": {"negative_preferences": ["neon"], "material_palette": []}}
    cfg = build_config(items, profile, keep=1)
    trf = TasteRejectionFunction(cfg)
    sel = trf.select(
        [
            Candidate("keep", embedding=[1.0, 0.0]),
            Candidate("drop", embedding=[0.0, 1.0]),
        ]
    )
    assert [v.candidate_id for v in sel.kept] == ["keep"]


def test_candidate_from_render_derives_aspect_ratio():
    render = {"id": "r1", "resolution": {"width": 1536, "height": 1024}, "embedding": [1.0]}
    cand = candidate_from_render(render, extra={"tags": ["cozy"], "colors": ["#efe7d8"]})
    assert cand.id == "r1"
    assert cand.aspect_ratio == pytest.approx(1.5)
    assert cand.tags == ["cozy"]
    assert cand.embedding == [1.0]


def test_candidate_extra_embedding_overrides_stored():
    render = {"id": "r1", "embedding": [0.0]}
    cand = candidate_from_render(render, extra={"embedding": [9.0]})
    assert cand.embedding == [9.0]
