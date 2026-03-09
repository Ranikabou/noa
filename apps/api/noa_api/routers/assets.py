"""Serve uploaded images from S3 (LocalStack). Streams bytes directly to avoid presigned URL issues."""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from noa_api.storage.s3 import _client as s3_client

BUCKET = os.environ.get("S3_BUCKET_ASSETS", "noa-assets")

router = APIRouter()


@router.get("/{storage_key:path}")
async def get_asset(storage_key: str):
    """Stream an S3 object by its storage key."""
    client = s3_client()
    try:
        obj = client.get_object(Bucket=BUCKET, Key=storage_key)
    except client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail="Asset not found")
    except Exception as e:
        if "NoSuchKey" in str(e) or "404" in str(e):
            raise HTTPException(status_code=404, detail="Asset not found")
        raise HTTPException(status_code=500, detail=str(e))

    content_type = obj.get("ContentType", "application/octet-stream")

    def stream():
        body = obj["Body"]
        while chunk := body.read(64 * 1024):
            yield chunk

    return StreamingResponse(
        stream(),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
