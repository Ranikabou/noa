import type { UUID, ISO8601 } from "./common.js";
import type { BBox, Point2D, ObservationType } from "./common.js";

export interface ParsedWall {
  id: string;
  geometry: number[][];
  confidence: number;
  observation_type: ObservationType;
}

export interface ParsedOpening {
  id: string;
  geometry: number[][];
  confidence: number;
  observation_type: ObservationType;
}

export interface ParsedRoom {
  id: string;
  geometry: number[][];
  confidence: number;
  observation_type: ObservationType;
}

export interface ParsedStair {
  id: string;
  geometry: unknown;
  confidence: number;
  observation_type: ObservationType;
}

export interface ParsedColumn {
  id: string;
  geometry: unknown;
  confidence: number;
  observation_type: ObservationType;
}

export interface ParsedAnnotation {
  id: string;
  geometry: unknown;
  confidence: number;
  observation_type: ObservationType;
}

export interface AmbiguityFlag {
  id: string;
  element_type: string;
  description: string;
  confidence: number;
  element_id?: string;
}

export interface ParsedPlan {
  schema_version: "1.0";
  id: UUID;
  floorplan_asset_id: UUID;
  parse_job_id: UUID;
  status: "pending" | "partial" | "complete" | "failed";
  confidence_overall: number;
  ambiguity_flags: AmbiguityFlag[];
  walls: ParsedWall[];
  openings: ParsedOpening[];
  rooms: ParsedRoom[];
  stairs: ParsedStair[];
  columns: ParsedColumn[];
  annotations: ParsedAnnotation[];
  bounding_box_px: BBox;
  coordinate_origin: Point2D;
  created_at: ISO8601;
}
