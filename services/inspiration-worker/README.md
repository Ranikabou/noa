# Inspiration Worker

CLIP embed + style profile builder. OpenCLIP ViT-L/14, 768-dim.

The embedding provider lives in `apps/api/noa_api/embeddings.py` and is invoked by
the `style_inference` job: every inspiration item is embedded and stored on
`inspiration_items.embedding` (positive items = the taste canon, negative items =
the rejection set), and the `StyleProfile.embedding_vector` is the positive-exemplar
centroid.

Backends are selected via `CLIP_BACKEND` (`auto` | `openclip` | `hash`). The real
`openclip` backend needs `open_clip_torch` + `torch` (`pip install -e "apps/api[clip]"`);
without them the provider uses a deterministic, non-semantic hash fallback so the
pipeline still runs in dev/CI. These vectors feed the taste rejection function —
see `apps/api/noa_api/taste/`.
