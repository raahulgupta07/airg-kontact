"""Pluggable file storage — local disk or S3-compatible (AWS S3, MinIO,
Backblaze B2, Cloudflare R2, Wasabi).

API (same for both backends):
    save_bytes(key, data: bytes, content_type: str = None) -> str
    save_file(key, src_path: str, content_type: str = None) -> str
    open_stream(key) -> file-like object
    get_local_path(key) -> str  (downloads to a temp file if S3)
    delete(key) -> bool
    delete_prefix(prefix) -> int
    exists(key) -> bool
    presigned_url(key, expires_seconds=3600) -> str | None
    backend_name() -> "local" | "s3"

Keys are POSIX-style:  uploads/<folder>/<filename>

Selection: STORAGE_BACKEND env var ("local" default, "s3" for cloud).

Required env for S3 backend:
    S3_BUCKET           bucket name
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
Optional:
    S3_ENDPOINT_URL     for MinIO / R2 / B2 (e.g. https://s3.eu-central-003.backblazeb2.com)
    S3_REGION           default "us-east-1"
    S3_PREFIX           optional key prefix (default "")
    S3_PUBLIC_BASE_URL  if bucket is public; else uses presigned URLs
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from typing import Optional

import config

log = logging.getLogger("kontact.storage")

BACKEND = (os.getenv("STORAGE_BACKEND") or "local").strip().lower()


# ─── LOCAL BACKEND ──────────────────────────────────────────────────

class LocalStorage:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _abs(self, key: str) -> str:
        # Defence in depth — never resolve outside base_dir
        rel = key.lstrip("/").replace("\\", "/")
        if ".." in rel.split("/"):
            raise ValueError(f"invalid key (traversal): {key}")
        path = os.path.normpath(os.path.join(self.base_dir, rel))
        if not (path == self.base_dir or path.startswith(self.base_dir + os.sep)):
            raise ValueError(f"key escapes base_dir: {key}")
        return path

    def save_bytes(self, key: str, data: bytes, content_type: str = None) -> str:
        p = self._abs(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        return key

    def save_file(self, key: str, src_path: str, content_type: str = None) -> str:
        p = self._abs(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if os.path.abspath(src_path) != p:
            shutil.copyfile(src_path, p)
        return key

    def open_stream(self, key: str):
        return open(self._abs(key), "rb")

    def get_local_path(self, key: str) -> str:
        p = self._abs(key)
        if not os.path.isfile(p):
            raise FileNotFoundError(key)
        return p

    def delete(self, key: str) -> bool:
        try:
            os.remove(self._abs(key))
            return True
        except (FileNotFoundError, OSError):
            return False

    def delete_prefix(self, prefix: str) -> int:
        p = self._abs(prefix)
        if not os.path.isdir(p):
            return 0
        n = 0
        for root, _, files in os.walk(p):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                    n += 1
                except OSError:
                    pass
        try:
            shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass
        return n

    def exists(self, key: str) -> bool:
        try:
            return os.path.isfile(self._abs(key))
        except ValueError:
            return False

    def presigned_url(self, key: str, expires_seconds: int = 3600) -> Optional[str]:
        return None  # served by FastAPI; no presigned URLs needed

    def backend_name(self) -> str:
        return "local"


# ─── S3 BACKEND ─────────────────────────────────────────────────────

class S3Storage:
    def __init__(self):
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError as e:
            raise RuntimeError(
                "boto3 not installed. Add 'boto3==1.35.0' to requirements.txt"
            ) from e

        self.bucket = os.getenv("S3_BUCKET") or ""
        if not self.bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 but S3_BUCKET not set")
        self.endpoint = os.getenv("S3_ENDPOINT_URL") or None
        self.region = os.getenv("S3_REGION") or "us-east-1"
        self.prefix = (os.getenv("S3_PREFIX") or "").strip("/")
        self.public_base = (os.getenv("S3_PUBLIC_BASE_URL") or "").rstrip("/") or None

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            region_name=self.region,
            config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3}),
        )
        log.info(
            "S3 storage initialised: bucket=%s endpoint=%s prefix=%s",
            self.bucket, self.endpoint or "(aws default)", self.prefix or "(root)",
        )

    def _full_key(self, key: str) -> str:
        k = key.lstrip("/").replace("\\", "/")
        if ".." in k.split("/"):
            raise ValueError(f"invalid key (traversal): {key}")
        return f"{self.prefix}/{k}" if self.prefix else k

    def save_bytes(self, key: str, data: bytes, content_type: str = None) -> str:
        kwargs = {"Bucket": self.bucket, "Key": self._full_key(key), "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type
        self.client.put_object(**kwargs)
        return key

    def save_file(self, key: str, src_path: str, content_type: str = None) -> str:
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_file(src_path, self.bucket, self._full_key(key), ExtraArgs=extra)
        return key

    def open_stream(self, key: str):
        obj = self.client.get_object(Bucket=self.bucket, Key=self._full_key(key))
        return obj["Body"]

    def get_local_path(self, key: str) -> str:
        """Download to a temp file (caller must clean up if needed)."""
        suffix = os.path.splitext(key)[1] or ""
        fd, tmp = tempfile.mkstemp(suffix=suffix, prefix="kontact-s3-")
        os.close(fd)
        try:
            self.client.download_file(self.bucket, self._full_key(key), tmp)
        except Exception:
            try: os.remove(tmp)
            except OSError: pass
            raise
        return tmp

    def delete(self, key: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=self._full_key(key))
            return True
        except Exception as e:
            log.warning("S3 delete failed for %s: %s", key, e)
            return False

    def delete_prefix(self, prefix: str) -> int:
        full = self._full_key(prefix)
        paginator = self.client.get_paginator("list_objects_v2")
        n = 0
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if not keys:
                continue
            self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})
            n += len(keys)
        return n

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._full_key(key))
            return True
        except Exception:
            return False

    def presigned_url(self, key: str, expires_seconds: int = 3600) -> Optional[str]:
        full = self._full_key(key)
        if self.public_base:
            return f"{self.public_base}/{full}"
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": full},
                ExpiresIn=expires_seconds,
            )
        except Exception as e:
            log.warning("presigned_url failed for %s: %s", key, e)
            return None

    def backend_name(self) -> str:
        return "s3"


# ─── singleton ──────────────────────────────────────────────────────

def _build():
    if BACKEND == "s3":
        return S3Storage()
    return LocalStorage(config.UPLOADS_DIR)


storage = _build()
log.info("Storage backend = %s", storage.backend_name())


# ─── convenience ────────────────────────────────────────────────────

def upload_key(folder: str, filename: str) -> str:
    """Build canonical storage key for an upload."""
    return f"{folder}/{filename}"
