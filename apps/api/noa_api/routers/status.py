"""SSE endpoint for project status. Replays project_events on reconnect via Last-Event-ID."""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from noa_api.db.models import Project as ProjectModel
from noa_api.db.session import SessionLocal
from noa_api.events import get_events_since

router = APIRouter()


async def _sse_stream(project_id: str, last_event_id: int | None):
    """Yield SSE-formatted events. Replay missed events, then heartbeat."""
    events = get_events_since(project_id, last_event_id)
    for seq, event_type, payload in events:
        data = json.dumps({"event": event_type, "data": payload})
        yield f"id: {seq}\ndata: {data}\n\n"

    # Heartbeat every 15s
    while True:
        await asyncio.sleep(15)
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        yield f'data: {{"event":"heartbeat","data":{{"timestamp":"{ts}"}}}}\n\n'


@router.get("/{project_id}/status")
async def project_status_sse(project_id: str, request: Request):
    """
    SSE stream of project events. Send Last-Event-ID header to replay missed events.
    """
    db = SessionLocal()
    try:
        proj = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
    finally:
        db.close()

    lid = request.headers.get("Last-Event-ID")
    try:
        last_seq = int(lid) if lid else None
    except (ValueError, TypeError):
        last_seq = None

    return StreamingResponse(
        _sse_stream(project_id, last_seq),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
