"""
services/s3_service.py
──────────────────────
AWS S3 operations: presigned upload/download URLs,
file deletion, export uploads.
All attachment storage references S3 keys — never local paths.
"""

from __future__ import annotations
import logging
import mimetypes
import uuid
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class S3Service:
    def __init__(self):
        self._client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
        )
        self._attachments_bucket = settings.S3_BUCKET_ATTACHMENTS
        self._exports_bucket = settings.S3_BUCKET_EXPORTS

    # ── Presigned upload URL ──────────────────────────────────────

    def create_presigned_upload(
        self,
        user_id: str,
        note_id: str,
        filename: str,
        content_type: Optional[str] = None,
    ) -> dict:
        """
        Generate a presigned POST URL so clients can upload
        directly to S3 without routing through the API server.
        Returns {upload_url, s3_key, attachment_id, expires_in}.
        """
        attachment_id = str(uuid.uuid4())
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        s3_key = f"attachments/{user_id}/{note_id}/{attachment_id}.{ext}"
        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        try:
            upload_url = self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._attachments_bucket,
                    "Key": s3_key,
                    "ContentType": content_type,
                    "ServerSideEncryption": "AES256",
                },
                ExpiresIn=300,   # 5 minutes to upload
                HttpMethod="PUT",
            )
            return {
                "upload_url": upload_url,
                "s3_key": s3_key,
                "attachment_id": attachment_id,
                "expires_in": 300,
            }
        except ClientError as e:
            logger.error(f"S3 presigned upload error: {e}")
            raise

    # ── Presigned download URL ────────────────────────────────────

    def create_presigned_download(self, s3_key: str, filename: str) -> str:
        """Generate a presigned GET URL for a specific attachment."""
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._attachments_bucket,
                    "Key": s3_key,
                    "ResponseContentDisposition": f'attachment; filename="{filename}"',
                },
                ExpiresIn=settings.S3_PRESIGNED_URL_EXPIRY,
            )
        except ClientError as e:
            logger.error(f"S3 presigned download error: {e}")
            raise

    # ── Upload export file ────────────────────────────────────────

    def upload_export(
        self,
        user_id: str,
        note_id: str,
        content: bytes,
        format: str,
        note_title: str,
    ) -> str:
        """Upload an exported note to S3 and return a presigned download URL."""
        ext_map = {"txt": "txt", "md": "md", "pdf": "pdf"}
        ext = ext_map.get(format, "txt")
        s3_key = f"exports/{user_id}/{note_id}/{note_title[:60]}.{ext}"

        content_types = {
            "txt": "text/plain",
            "md": "text/markdown",
            "pdf": "application/pdf",
        }

        self._client.put_object(
            Bucket=self._exports_bucket,
            Key=s3_key,
            Body=content,
            ContentType=content_types.get(format, "application/octet-stream"),
            ServerSideEncryption="AES256",
        )

        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._exports_bucket, "Key": s3_key},
            ExpiresIn=3600,
        )

    # ── Delete ────────────────────────────────────────────────────

    def delete_attachment(self, s3_key: str):
        try:
            self._client.delete_object(
                Bucket=self._attachments_bucket,
                Key=s3_key,
            )
        except ClientError as e:
            logger.error(f"S3 delete error: {e}")

    def delete_attachments_batch(self, s3_keys: list[str]):
        if not s3_keys:
            return
        objects = [{"Key": k} for k in s3_keys]
        try:
            self._client.delete_objects(
                Bucket=self._attachments_bucket,
                Delete={"Objects": objects, "Quiet": True},
            )
        except ClientError as e:
            logger.error(f"S3 batch delete error: {e}")

    # ── Health ────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self._attachments_bucket)
            return True
        except ClientError:
            return False


s3_service = S3Service()
