"""MinIO/S3 package storage (optional; default is the local courses directory)."""
from __future__ import annotations

import os
from datetime import timedelta


def minio_client():
    from minio import Minio

    c = Minio(os.environ.get("MINIO_ENDPOINT", "minio:9000"), access_key=os.environ.get("MINIO_ACCESS_KEY", "rideprep"),
              secret_key=os.environ.get("MINIO_SECRET_KEY", "rideprep-secret"), secure=os.environ.get("MINIO_SECURE") == "1")
    bucket = os.environ.get("MINIO_BUCKET", "courses")
    if not c.bucket_exists(bucket):
        c.make_bucket(bucket)
    return c, bucket


def signed_url(course_id: str, path: str) -> str:
    c, bucket = minio_client()
    return c.presigned_get_object(bucket, f"{course_id}/{path}", expires=timedelta(hours=6))
