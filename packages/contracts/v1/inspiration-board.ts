import type { UUID, ISO8601 } from "./common.js";

export interface InspirationBoard {
  schema_version: "1.0";
  id: UUID;
  project_id: UUID;
  name: string;
  description: string | null;
  item_count: number;
  is_primary: boolean;
  style_profile_id: UUID | null;
  style_inference_status:
    | "pending"
    | "running"
    | "ready"
    | "stale"
    | "failed";
  created_at: ISO8601;
  updated_at: ISO8601;
}
