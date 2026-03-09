from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class User(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    email: str
    display_name: str
    avatar_url: str | None
    role: Literal["owner", "member", "viewer", "admin"]
    plan: Literal["free", "pro", "team", "enterprise"]
    auth_provider: Literal["email", "google", "github"]
    auth_provider_id: str
    email_verified: bool
    created_at: str
    updated_at: str
    last_login_at: str | None
