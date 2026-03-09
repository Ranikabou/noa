import type { UUID, ISO8601 } from "./common.js";

export interface WallEdit {
  edit_type: "wall";
  [key: string]: unknown;
}

export interface RoomEdit {
  edit_type: "room";
  [key: string]: unknown;
}

export interface OpeningEdit {
  edit_type: "opening";
  [key: string]: unknown;
}

export interface StairEdit {
  edit_type: "stair";
  [key: string]: unknown;
}

export interface ScaleEdit {
  edit_type: "scale";
  [key: string]: unknown;
}

export interface LabelEdit {
  edit_type: "label";
  [key: string]: unknown;
}

export interface DeleteEdit {
  edit_type: "delete";
  [key: string]: unknown;
}

export interface AddEdit {
  edit_type: "add";
  [key: string]: unknown;
}

export type PlanEdit =
  | WallEdit
  | RoomEdit
  | OpeningEdit
  | StairEdit
  | ScaleEdit
  | LabelEdit
  | DeleteEdit
  | AddEdit;

export interface AnnotationSession {
  schema_version: "1.0";
  id: UUID;
  project_id: UUID;
  parsed_plan_id: UUID;
  user_id: UUID;
  status: "open" | "submitted" | "applying" | "applied" | "rejected";
  trigger: "ambiguity_flag" | "user_initiated" | "critique_failure";
  edits: PlanEdit[];
  submitted_at: ISO8601 | null;
  applied_at: ISO8601 | null;
  downstream_recomputed: boolean;
  export_to_training: boolean;
  created_at: ISO8601;
  updated_at: ISO8601;
}
