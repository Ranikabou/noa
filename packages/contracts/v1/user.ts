import type { UUID, ISO8601 } from "./common.js";

export interface User {
  schema_version: "1.0";
  id: UUID;
  email: string;
  display_name: string;
  avatar_url: string | null;
  role: "owner" | "member" | "viewer" | "admin";
  plan: "free" | "pro" | "team" | "enterprise";
  auth_provider: "email" | "google" | "github";
  auth_provider_id: string;
  email_verified: boolean;
  created_at: ISO8601;
  updated_at: ISO8601;
  last_login_at: ISO8601 | null;
}
