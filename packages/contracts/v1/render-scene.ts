import type { UUID, ISO8601 } from "./common.js";

export interface Camera {
  id: string;
  [key: string]: unknown;
}

export interface LightingSetup {
  [key: string]: unknown;
}

export interface EnvironmentMap {
  [key: string]: unknown;
}

export interface MaterialAssignment {
  [key: string]: unknown;
}

export interface RenderVariant {
  id: string;
  [key: string]: unknown;
}

export interface RenderScene {
  schema_version: "1.0";
  id: UUID;
  canonical_model_id: UUID;
  style_profile_id: UUID | null;
  cameras: Camera[];
  lighting_setup: LightingSetup;
  environment: EnvironmentMap;
  material_assignments: MaterialAssignment[];
  render_settings: {
    engine: "cycles" | "eevee";
    samples: number;
    resolution: { width: number; height: number };
    output_formats: ("jpeg" | "png")[];
  };
  variants: RenderVariant[];
  created_at: ISO8601;
}
