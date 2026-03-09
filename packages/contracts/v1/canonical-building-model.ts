import type { UUID, ISO8601 } from "./common.js";
import type { ObservationType } from "./common.js";

export type ElementId = string;

export interface Level {
  id: string;
  [key: string]: unknown;
}

export interface Wall {
  id: string;
  [key: string]: unknown;
}

export interface Slab {
  id: string;
  [key: string]: unknown;
}

export interface RoofElement {
  id: string;
  [key: string]: unknown;
}

export interface Door {
  id: string;
  [key: string]: unknown;
}

export interface Window {
  id: string;
  [key: string]: unknown;
}

export interface Stair {
  id: string;
  [key: string]: unknown;
}

export interface Column {
  id: string;
  [key: string]: unknown;
}

export interface Beam {
  id: string;
  [key: string]: unknown;
}

export interface Room {
  id: string;
  [key: string]: unknown;
}

export interface MeshRef {
  id: string;
  [key: string]: unknown;
}

export interface Primitive {
  id: string;
  [key: string]: unknown;
}

export interface ElementProvenance {
  element_id: string;
  [key: string]: unknown;
}

export interface CanonicalBuildingModel {
  schema_version: "1.0";
  id: UUID;
  project_id: UUID;
  spatial_graph_id: UUID;
  style_profile_id: UUID | null;
  elements: {
    levels: Level[];
    walls: Wall[];
    slabs: Slab[];
    roofs: RoofElement[];
    doors: Door[];
    windows: Window[];
    stairs: Stair[];
    columns: Column[];
    beams: Beam[];
    rooms: Room[];
  };
  geometry_layer: {
    meshes: MeshRef[];
    parametric_primitives: Primitive[];
  };
  provenance: ElementProvenance[];
  observation_types: Record<ElementId, ObservationType>;
  version: number;
  created_at: ISO8601;
  updated_at: ISO8601;
}
