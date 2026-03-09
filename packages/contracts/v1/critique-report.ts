import type { UUID, ISO8601 } from "./common.js";

export interface CritiqueIssue {
  code: string;
  message: string;
  severity: string;
  element_id?: string;
  [key: string]: unknown;
}

export interface CritiqueReport {
  schema_version: "1.0";
  id: UUID;
  canonical_model_id: UUID;
  critique_job_id: UUID;
  scores: {
    plan_fidelity: number;
    inspiration_alignment: number;
    architectural_plausibility: number;
    geometric_consistency: number;
    render_coherence: number;
  };
  issues: CritiqueIssue[];
  suggestions: string[];
  blocking: boolean;
  created_at: ISO8601;
}
