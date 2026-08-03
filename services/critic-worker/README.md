# Critic Worker

Automated + LLM critique. Plan fidelity, inspiration alignment, geometric consistency.

## Taste rejection function

The aesthetic half of the critique is a **rejection function**, not a generator:
the render-worker overgenerates candidates and the critic keeps only the few that
survive. It scores each candidate by contrastive distance to a tight reference
corpus (positive inspiration items) minus a densely-sampled boundary of rejections
(negative items), applies hard constraints (refused motifs, fixed palette, crop
grammar), and cuts to a small `keep`. The kept/seen selectivity ratio *is* the
taste.

The implementation lives in `apps/api/noa_api/taste/` (pure stdlib, fully unit
tested) and feeds `CritiqueReport.scores.inspiration_alignment` /
`render_coherence`. See that package's README for the design and the mapping to
NOA's `InspirationItem`, `StyleProfile`, and `RenderImage` records.
