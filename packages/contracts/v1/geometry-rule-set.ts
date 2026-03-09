import type { UUID, ISO8601 } from "./common.js";

export interface GlazingRatioRule {
  rule_type: "glazing_ratio";
  target_ratio: number;
  applies_to: "exterior_walls" | "all_walls";
  confidence: number;
}

export interface OverhangRule {
  rule_type: "overhang";
  [key: string]: unknown;
}

export interface RoofRule {
  rule_type: "roof_form";
  form: "flat" | "shed" | "gabled" | "hipped" | "butterfly";
  pitch_degrees: number | null;
  confidence: number;
}

export interface FacadeGridRule {
  rule_type: "facade_grid";
  [key: string]: unknown;
}

export interface FloorHeightRule {
  rule_type: "floor_height";
  [key: string]: unknown;
}

export interface MaterialHintRule {
  rule_type: "material_hint";
  [key: string]: unknown;
}

export type GeometryRule =
  | GlazingRatioRule
  | OverhangRule
  | RoofRule
  | FacadeGridRule
  | FloorHeightRule
  | MaterialHintRule;

export interface GeometryRuleSet {
  schema_version: "1.0";
  id: UUID;
  style_profile_id: UUID;
  derived_at: ISO8601;
  confidence_overall: number;
  rules: GeometryRule[];
}
