import type { UUID, ISO8601 } from "./common.js";
import type { ScaleInfo } from "./common.js";

export interface FloorplanAsset {
  schema_version: "1.0";
  id: UUID;
  project_id: UUID;
  source_type: "pdf" | "image" | "cad_export" | "scan" | "hand_marked";
  storage_key: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  dimensions_px: { width: number; height: number } | null;
  page_count: number;
  detected_scale: ScaleInfo | null;
  upload_status: "pending" | "ready" | "failed";
  ingestion_job_id: UUID | null;
  created_at: ISO8601;
}
