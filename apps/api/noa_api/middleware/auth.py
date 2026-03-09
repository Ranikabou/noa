"""JWT auth middleware — stub for Phase 0. Validates Bearer token when present."""
import os
from typing import Callable
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_EXPIRY_SECONDS = int(os.environ.get("JWT_EXPIRY_SECONDS", "86400"))


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Stub: accepts any Bearer token or skips if no Authorization header (for health)."""

    async def dispatch(self, request: Request, call_next: Callable):
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            # Stub: in production validate JWT and set request.state.user_id
            token = auth[7:]
            request.state.user_id = token[:36] if len(token) >= 36 else "stub-user"
        else:
            request.state.user_id = None
        return await call_next(request)
