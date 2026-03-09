import type { UUID, ISO8601 } from "./common.js";

export interface RenderImage {
  schema_version: "1.0";
  id: UUID;
  render_scene_id: UUID;
  canonical_model_id: UUID;
  render_job_id: UUID;
  camera_preset:
    | "exterior_3q"
    | "exterior_street"
    | "aerial_45"
    | "courtyard"
    | "interior_living";
  lighting_variant: "midday" | "golden_hour" | "overcast" | "dusk" | "night";
  engine: "eevee" | "cycles";
  resolution: { width: number; height: number };
  storage_key_jpeg: string | null;
  storage_key_png: string | null;
  render_duration_ms: number | null;
  quality_scores: {
    niqe: number | null;
    pixel_coverage: number | null;
    inspiration_alignment: number | null;
  };
  status: "pending" | "rendering" | "ready" | "failed";
  error_message: string | null;
  created_at: ISO8601;
  updated_at: ISO8601;
}
