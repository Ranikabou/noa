import type { UUID, ISO8601 } from "./common.js";

export type ElementType = string;

export interface ExportPackage {
  schema_version: "1.0";
  id: UUID;
  canonical_model_id: UUID;
  format: "glb" | "obj" | "dxf" | "ifc" | "3dm" | "blend";
  storage_key: string;
  geometry_fidelity: "full" | "simplified" | "lod1";
  semantic_fidelity: "full" | "geometry_only" | "rooms_only";
  supported_elements: ElementType[];
  conversion_limitations: string[];
  export_job_id: UUID;
  created_at: ISO8601;
}
