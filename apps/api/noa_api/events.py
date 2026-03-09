"""Project events for SSE. Writes to project_events table; SSE replays via Last-Event-ID."""
import json
from datetime import datetime, timezone

from sqlalchemy import text

from noa_api.db.session import SessionLocal


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def emit_project_event(
    project_id: str,
    event_type: str,
    payload: dict,
    *,
    job_id: str | None = None,
    user_id: str | None = None,
) -> int:
    """
    Append event to project_events. Returns sequence_no for Last-Event-ID.
    """
    db = SessionLocal()
    try:
        # Get next sequence number
        r = db.execute(
            text(
                """
            SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_seq
            FROM project_events WHERE project_id = :pid
            """
            ),
            {"pid": project_id},
        )
        seq = r.scalar()
        db.execute(
            text(
                """
            INSERT INTO project_events (project_id, event_type, sequence_no, payload, job_id, user_id)
            VALUES (:pid, :etype, :seq, CAST(:payload AS jsonb), :jid, :uid)
            """
            ),
            {
                "pid": project_id,
                "etype": event_type,
                "seq": seq,
                "payload": json.dumps(payload),
                "jid": job_id,
                "uid": user_id,
            },
        )
        db.commit()
        return seq
    finally:
        db.close()


def get_events_since(project_id: str, last_event_id: int | None) -> list[tuple[int, str, dict]]:
    """
    Fetch events for SSE replay. Returns [(sequence_no, event_type, payload), ...].
    """
    db = SessionLocal()
    try:
        if last_event_id is not None:
            r = db.execute(
                text(
                    """
                SELECT sequence_no, event_type, payload
                FROM project_events
                WHERE project_id = :pid AND sequence_no > :last
                ORDER BY sequence_no
                """
                ),
                {"pid": project_id, "last": last_event_id},
            )
        else:
            r = db.execute(
                text(
                    """
                SELECT sequence_no, event_type, payload
                FROM project_events
                WHERE project_id = :pid
                ORDER BY sequence_no
                """
                ),
                {"pid": project_id},
            )
        return [(row[0], row[1], row[2]) for row in r.fetchall()]
    finally:
        db.close()
