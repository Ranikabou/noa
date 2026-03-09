"""S3 storage client. Uses LocalStack in dev via S3_ENDPOINT_URL."""
import os
import uuid
from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

BUCKET_ASSETS = os.environ.get("S3_BUCKET_ASSETS", "noa-assets")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL")  # http://localhost:4566 for LocalStack


def _client():
    kwargs = {"region_name": AWS_REGION}
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
        # LocalStack doesn't check credentials but boto3 requires them
        kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
    return boto3.client(
        "s3",
        config=Config(signature_version="s3v4"),
        **kwargs,
    )


def ensure_bucket() -> None:
    """Create bucket if it does not exist. Call at startup."""
    client = _client()
    try:
        client.head_bucket(Bucket=BUCKET_ASSETS)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            client.create_bucket(Bucket=BUCKET_ASSETS)
        else:
            raise


def upload_floorplan(
    project_id: str,
    file_obj: BinaryIO,
    filename: str,
    content_type: str,
) -> tuple[str, int]:
    """
    Upload floorplan file to S3. Returns (storage_key, file_size_bytes).
    Key format: floorplans/{project_id}/{uuid}_{sanitized_filename}
    """
    client = _client()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[:64]
    key = f"floorplans/{project_id}/{uuid.uuid4().hex}_{safe_name}"

    file_obj.seek(0, 2)
    size = file_obj.tell()
    file_obj.seek(0)

    client.upload_fileobj(
        file_obj,
        BUCKET_ASSETS,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return key, size


def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generate presigned GET URL for private object."""
    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_ASSETS, "Key": key},
        ExpiresIn=expires_in,
    )
