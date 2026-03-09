import type { UUID, ISO8601 } from "./common.js";

export type MassingTendency = string;
export type FacadeRhythm = string;
export type LightingMood = string;
export type SurfaceLanguage = string;
export type RoofTendency = string;

export interface MaterialPaletteEntry {
  name: string;
  [key: string]: unknown;
}

export interface StyleProfile {
  schema_version: "1.0";
  id: UUID;
  inspiration_board_id: UUID;
  inference_job_id: UUID;
  embedding_vector: number[];
  style_signals: {
    massing_tendency: MassingTendency;
    facade_rhythm: FacadeRhythm;
    material_palette: MaterialPaletteEntry[];
    lighting_mood: LightingMood;
    surface_language: SurfaceLanguage;
    compositional_balance: "symmetric" | "asymmetric" | "dynamic";
    emotional_tone: string[];
    negative_preferences: string[];
    roof_tendency: RoofTendency;
    glazing_ratio: number;
    overhang_tendency: "deep" | "minimal" | "none";
  };
  confidence_per_signal: Record<string, number>;
  source_image_ids: UUID[];
  created_at: ISO8601;
}
