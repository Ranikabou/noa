import type { UUID, ISO8601 } from "./common.js";

export type JobType = string;

export interface JobUpdateEvent {
  event: "job_update";
  data: {
    job_id: UUID;
    job_type: JobType;
    status: "queued" | "running" | "complete" | "failed" | "retrying";
    retry_count: number;
    progress: number;
    stage: string | null;
    result_ref: UUID | null;
    error: { code: string; message: string } | null;
    timestamp: ISO8601;
  };
}

export interface ProjectStatusEvent {
  event: "project_status";
  data: Record<string, unknown>;
}

export interface StageProgressEvent {
  event: "stage_progress";
  data: Record<string, unknown>;
}

export interface AmbiguityFlagEvent {
  event: "ambiguity_flag";
  data: {
    flag_id: UUID;
    element_type: string;
    description: string;
    confidence: number;
    requires_user_action: boolean;
    timestamp: ISO8601;
  };
}

export interface CritiqueSummaryEvent {
  event: "critique_summary";
  data: Record<string, unknown>;
}

export interface HeartbeatEvent {
  event: "heartbeat";
  data: { timestamp: ISO8601 };
}

export type SSEEvent =
  | JobUpdateEvent
  | ProjectStatusEvent
  | StageProgressEvent
  | AmbiguityFlagEvent
  | CritiqueSummaryEvent
  | HeartbeatEvent;
