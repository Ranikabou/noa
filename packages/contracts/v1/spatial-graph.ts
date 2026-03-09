import type { UUID, ISO8601 } from "./common.js";

export interface SpatialNode {
  id: string;
  [key: string]: unknown;
}

export interface SpatialEdge {
  id: string;
  [key: string]: unknown;
}

export interface LevelDescriptor {
  id: string;
  [key: string]: unknown;
}

export interface CirculationGraph {
  [key: string]: unknown;
}

export interface SpatialGraph {
  schema_version: "1.0";
  id: UUID;
  parsed_plan_id: UUID;
  nodes: SpatialNode[];
  edges: SpatialEdge[];
  levels: LevelDescriptor[];
  circulation_graph: CirculationGraph;
  room_adjacency_matrix: number[][];
  scale_meters_per_unit: number;
  coordinate_system: "metric" | "imperial";
  created_at: ISO8601;
}
