"""
Cliente para object storage (MinIO localmente, S3 en producción).

Decisión: usamos `boto3` (SDK oficial de AWS) configurado contra el
endpoint de MinIO. La API S3 es un estándar de facto, así que el mismo
código funciona contra MinIO, AWS S3, Cloudflare R2, Backblaze B2, etc.

Alternativas:
  - aioboto3   : versión async de boto3. Útil cuando el throughput importa.
  - minio-py   : SDK oficial de MinIO. Funciona, pero ata al ecosistema.
"""

from __future__ import annotations

from typing import Any, cast

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from cip.config import get_settings
from cip.logging_setup import get_logger

log = get_logger(__name__)


class ObjectStorage:
    """Wrapper sobre boto3 con los métodos que necesitamos."""

    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4",
                # path-style addressing: imprescindible para MinIO; AWS S3 lo soporta también.
                s3={"addressing_style": "path"},
            ),
        )

    def ensure_bucket(self) -> None:
        """Crea el bucket si no existe. Idempotente."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            log.debug("bucket_exists", bucket=self.bucket)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                log.info("creating_bucket", bucket=self.bucket)
                self.client.create_bucket(Bucket=self.bucket)
            else:
                raise

    def put_object(
        self,
        key: str,
        body: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Sube un objeto y devuelve la key."""
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        log.debug("object_uploaded", bucket=self.bucket, key=key, size=len(body))
        return key

    def get_object(self, key: str) -> bytes:
        """Descarga un objeto."""
        resp: dict[str, Any] = self.client.get_object(Bucket=self.bucket, Key=key)
        return cast(bytes, resp["Body"].read())

    def object_exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            http_status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if error_code in ("404", "NoSuchKey", "NotFound") or http_status == 404:
                return False
            raise

    def presigned_get_url(self, key: str, expires_seconds: int = 3600) -> str:
        """Genera una URL temporal para descargar un objeto."""
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
        return cast(str, url)
