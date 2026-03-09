import type { UUID, ISO8601 } from "./common.js";

export interface Project {
  schema_version: "1.0";
  id: UUID;
  name: string;
  owner_id: UUID;
  status: "draft" | "processing" | "ready" | "error";
  floorplan_asset_id: UUID | null;
  inspiration_board_id: UUID | null;
  canonical_model_id: UUID | null;
  metadata: Record<string, unknown>;
  created_at: ISO8601;
  updated_at: ISO8601;
}
