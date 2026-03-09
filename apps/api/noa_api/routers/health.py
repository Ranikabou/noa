"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    """Liveness/readiness. Returns 200 when service is up."""
    return {"status": "ok", "service": "noa-api"}
