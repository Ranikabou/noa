/** Common types for NOA canonical contracts. Schema version 1.0. */

export type UUID = string;
export type ISO8601 = string;

export interface BBox {
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
}

export interface Point2D {
  x: number;
  y: number;
}

export type ObservationType = "observed" | "inferred" | "assumed_default";

export interface ScaleInfo {
  px_per_meter: number;
  confidence: number;
  method: "barscale" | "dimension_text" | "known_element" | "assumed";
}
