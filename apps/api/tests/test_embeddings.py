"""Image embedding provider — exercised through the deterministic hash backend.

The openclip backend needs torch and is covered by its own integration setup; here
we pin ``CLIP_BACKEND=hash`` so the contract (dimensionality, unit norm,
determinism, distinctness, provenance) is verifiable anywhere.
"""
import math

import pytest

from noa_api import embeddings


@pytest.fixture(autouse=True)
def _force_hash_backend(monkeypatch):
    monkeypatch.setenv("CLIP_BACKEND", "hash")


def _norm(v):
    return math.sqrt(sum(x * x for x in v))


def test_dimensionality_and_unit_norm():
    v = embeddings.embed_image(b"some-image-bytes")
    assert len(v) == embeddings.DIM == 768
    assert _norm(v) == pytest.approx(1.0, abs=1e-6)


def test_determinism_same_bytes_same_vector():
    a = embeddings.embed_image(b"identical")
    b = embeddings.embed_image(b"identical")
    assert a == b


def test_distinct_bytes_give_distinct_vectors():
    a = embeddings.embed_image(b"image-a")
    b = embeddings.embed_image(b"image-b")
    assert a != b
    # And they are not trivially near-identical.
    cos = sum(x * y for x, y in zip(a, b))
    assert cos < 0.99


def test_batch_matches_individual_and_preserves_order():
    imgs = [b"one", b"two", b"three"]
    batch = embeddings.embed_images(imgs)
    assert len(batch) == 3
    assert batch[0] == embeddings.embed_image(b"one")
    assert batch[2] == embeddings.embed_image(b"three")


def test_empty_batch():
    assert embeddings.embed_images([]) == []


def test_active_model_and_is_semantic_under_hash():
    assert embeddings.active_model() == "hash-fallback"
    assert embeddings.is_semantic() is False


def test_no_zero_vectors():
    # The whole point: the old all-zeros placeholder is gone. Even trivial input
    # yields a non-degenerate unit vector the manifold can measure against.
    v = embeddings.embed_image(b"")
    assert _norm(v) == pytest.approx(1.0, abs=1e-6)
    assert any(x != 0.0 for x in v)
