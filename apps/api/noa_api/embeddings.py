"""Image embeddings — the vector space the taste manifold lives in.

The taste filter (`noa_api.taste`) measures distance to a corpus. That only means
anything once images become vectors in a *shared, semantic* space: the exemplars,
the rejections, and every render candidate must be embedded by the same model or
their cosine distances are noise. This module is that single source of truth.

Two backends, chosen at runtime:

- **openclip** — real CLIP ViT-L/14, 768-dim, L2-normalised. This is the semantic
  embedding that gives the manifold actual taste. Requires ``open_clip_torch`` +
  ``torch`` (heavy; GPU optional). The model loads once and is cached.
- **hash** — a deterministic, dependency-free fallback. It maps image bytes to a
  stable normalised vector with **no semantic meaning**. Its only jobs are to keep
  the pipeline runnable in dev/CI without torch and to prove the wiring end-to-end.
  It is *not* taste — it just gives the manifold a non-degenerate geometry to
  operate on so nothing downstream sees the old all-zeros vector.

Selection is via ``CLIP_BACKEND`` (``auto`` | ``openclip`` | ``hash``); ``auto``
uses openclip when importable and falls back to hash. Every produced vector is
tagged with :func:`active_model` so a hash vector can never be mistaken for CLIP,
and a future check can refuse to compare across models.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import struct
from typing import Sequence

logger = logging.getLogger("noa.embeddings")

#: CLIP ViT-L/14 image-embedding dimensionality.
DIM = 768

# open_clip architecture + checkpoint. "openai" is the original CLIP weights.
_CLIP_MODEL = os.environ.get("CLIP_MODEL", "ViT-L-14")
_CLIP_PRETRAINED = os.environ.get("CLIP_PRETRAINED", "openai")

_HASH_MODEL_NAME = "hash-fallback"
_CLIP_MODEL_NAME = "clip-vit-l-14"  # matches the InspirationItem contract literal

# Lazily-loaded, cached (model, preprocess) for the openclip backend.
_clip_cache: tuple | None = None


def _select_backend() -> str:
    """Resolve the active backend from ``CLIP_BACKEND`` (default ``auto``)."""
    choice = os.environ.get("CLIP_BACKEND", "auto").strip().lower()
    if choice in ("openclip", "hash"):
        return choice
    # auto: prefer real CLIP when the libraries are importable.
    try:
        import open_clip  # noqa: F401
        import torch  # noqa: F401

        return "openclip"
    except Exception:
        return "hash"


def active_model() -> str:
    """The model name for the backend that would run now (for provenance)."""
    return _CLIP_MODEL_NAME if _select_backend() == "openclip" else _HASH_MODEL_NAME


def is_semantic() -> bool:
    """True when the active backend produces real (CLIP) embeddings."""
    return _select_backend() == "openclip"


# --------------------------------------------------------------------------- #
# openclip backend
# --------------------------------------------------------------------------- #


def _load_clip():
    global _clip_cache
    if _clip_cache is None:
        import open_clip
        import torch

        model, _, preprocess = open_clip.create_model_and_transforms(
            _CLIP_MODEL, pretrained=_CLIP_PRETRAINED
        )
        model.eval()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        _clip_cache = (model, preprocess, device)
        logger.info("Loaded CLIP %s/%s on %s", _CLIP_MODEL, _CLIP_PRETRAINED, device)
    return _clip_cache


def _clip_embed_batch(images: Sequence[bytes]) -> list:
    import torch
    from PIL import Image

    model, preprocess, device = _load_clip()
    tensors = [
        preprocess(Image.open(io.BytesIO(b)).convert("RGB")) for b in images
    ]
    batch = torch.stack(tensors).to(device)
    with torch.no_grad():
        feats = model.encode_image(batch)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats.cpu().tolist()


# --------------------------------------------------------------------------- #
# hash fallback backend
# --------------------------------------------------------------------------- #


def _hash_embed(data: bytes, dim: int = DIM) -> list:
    """Deterministic, normalised, *non-semantic* vector from raw image bytes.

    Same bytes → same vector; different bytes → almost-certainly different vector.
    Built by expanding a SHA-256 keystream into ``dim`` floats in ``[-1, 1)`` and
    L2-normalising, so it sits on the unit sphere exactly like a CLIP vector and
    keeps cosine geometry well-defined. It carries no meaning about the image.
    """
    values: list = []
    counter = 0
    while len(values) < dim:
        block = hashlib.sha256(data + counter.to_bytes(8, "big")).digest()
        # 32 bytes → 8 uint32 → 8 floats in [-1, 1)
        for u in struct.unpack(">8I", block):
            if len(values) >= dim:
                break
            values.append(u / 2**31 - 1.0)
        counter += 1

    norm = sum(v * v for v in values) ** 0.5 or 1.0
    return [v / norm for v in values]


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #


def embed_images(images: Sequence[bytes]) -> list:
    """Embed a batch of raw image bytes into unit-norm vectors of length :data:`DIM`.

    Uses the active backend for the whole batch, so every vector shares a space.
    An image that fails to decode under the CLIP backend falls back to a hash
    vector for that item (logged), rather than dropping it and desyncing indices.
    """
    if not images:
        return []

    backend = _select_backend()
    if backend == "openclip":
        try:
            return _clip_embed_batch(images)
        except Exception as e:  # pragma: no cover - depends on torch runtime
            logger.warning("CLIP embedding failed (%s); using hash fallback", e)
            return [_hash_embed(b) for b in images]

    return [_hash_embed(b) for b in images]


def embed_image(data: bytes) -> list:
    """Embed a single image's bytes. See :func:`embed_images`."""
    return embed_images([data])[0]
