import type { UUID, ISO8601 } from "./common.js";

export interface ItemAnnotation {
  [key: string]: unknown;
}

export interface HighlightedElement {
  [key: string]: unknown;
}

export interface RejectedElement {
  [key: string]: unknown;
}

export interface InspirationItem {
  schema_version: "1.0";
  id: UUID;
  board_id: UUID;
  source_type: "upload" | "curated" | "url_import";
  storage_key: string | null;
  source_url: string | null;
  thumbnail_key: string | null;
  embedding: number[] | null;
  embedding_model: "clip-vit-l-14" | null;
  weight: number;
  sentiment: "positive" | "negative";
  annotations: ItemAnnotation[];
  highlighted_elements: HighlightedElement[];
  rejected_elements: RejectedElement[];
  upload_status: "pending" | "ready" | "failed";
  created_at: ISO8601;
}
