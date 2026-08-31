"""Where uploaded media lives.

Two backends behind one interface:

  LocalStorage  — writes under backend/media/, served by FastAPI at /media/...
                  Default, and what local development uses.
  R2Storage     — Cloudflare R2 (S3-compatible). Selected automatically when the
                  R2_* environment variables are present.

R2 is the production choice because it has no egress fees and sits on the CDN
the site already fronts with, so venue photos are served from the edge rather
than off the API box's disk — where they would also not survive a redeploy
unless the path happened to be a mounted volume.

Configure R2 with:

  R2_ACCOUNT_ID          Cloudflare account id
  R2_ACCESS_KEY_ID       R2 API token key id
  R2_SECRET_ACCESS_KEY   R2 API token secret
  R2_BUCKET              bucket name
  R2_PUBLIC_BASE_URL     public origin for reads, no trailing slash, e.g.
                         https://media.karaokespot.us  (a custom domain bound
                         to the bucket, or its r2.dev URL)

All five must be set; if any is missing we fall back to local storage rather
than half-configure and fail at the first upload.
"""

from __future__ import annotations

import os
import pathlib
from typing import Protocol


class Storage(Protocol):
    """Somewhere to put a blob and get a URL back."""

    def save(self, data: bytes, filename: str, content_type: str) -> str:
        """Store bytes under `filename`; return the URL clients should load."""
        ...

    def delete(self, url: str) -> None:
        """Best-effort removal. Never raises — a leaked object is not worth
        failing a user's request over."""
        ...


class LocalStorage:
    """Files on the API server's disk, served back by FastAPI."""

    def __init__(self, media_dir: pathlib.Path, url_prefix: str = "/media/venues") -> None:
        self.media_dir = media_dir
        self.url_prefix = url_prefix.rstrip("/")

    def save(self, data: bytes, filename: str, content_type: str) -> str:
        self.media_dir.mkdir(parents=True, exist_ok=True)
        (self.media_dir / filename).write_bytes(data)
        return f"{self.url_prefix}/{filename}"

    def delete(self, url: str) -> None:
        if not url or not url.startswith(self.url_prefix):
            return
        # Take only the final path segment — the stored URL is ours, but this
        # keeps a malformed value from escaping the media directory.
        name = pathlib.PurePosixPath(url).name
        if not name:
            return
        try:
            (self.media_dir / name).unlink(missing_ok=True)
        except OSError:
            pass


class R2Storage:
    """Cloudflare R2 via its S3-compatible API."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        public_base_url: str,
        key_prefix: str = "venues",
    ) -> None:
        import boto3  # imported lazily so local installs need not have it
        from botocore.config import Config

        self.bucket = bucket
        self.public_base_url = public_base_url.rstrip("/")
        self.key_prefix = key_prefix.strip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            # R2 ignores regions but the SDK insists on one.
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    def _key(self, filename: str) -> str:
        return f"{self.key_prefix}/{filename}" if self.key_prefix else filename

    def save(self, data: bytes, filename: str, content_type: str) -> str:
        key = self._key(filename)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            # These are immutable: a new upload gets a new random name, so the
            # old URL is never reused and can be cached indefinitely.
            CacheControl="public, max-age=31536000, immutable",
        )
        return f"{self.public_base_url}/{key}"

    def delete(self, url: str) -> None:
        if not url or not url.startswith(self.public_base_url):
            return
        key = url[len(self.public_base_url):].lstrip("/")
        if not key:
            return
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:
            # An orphaned object costs a fraction of a cent; a failed delete
            # must not break the request that triggered it.
            pass


R2_ENV_VARS = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_BASE_URL",
)


def build_storage(media_dir: pathlib.Path) -> Storage:
    """Pick a backend from the environment. R2 when fully configured, else disk."""
    values = {name: os.environ.get(name, "").strip() for name in R2_ENV_VARS}
    missing = [name for name, value in values.items() if not value]

    if not missing:
        try:
            return R2Storage(
                account_id=values["R2_ACCOUNT_ID"],
                access_key_id=values["R2_ACCESS_KEY_ID"],
                secret_access_key=values["R2_SECRET_ACCESS_KEY"],
                bucket=values["R2_BUCKET"],
                public_base_url=values["R2_PUBLIC_BASE_URL"],
            )
        except ImportError:
            print("[Storage] R2 configured but boto3 is not installed — using local disk", flush=True)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[Storage] R2 setup failed ({exc}) — using local disk", flush=True)
    elif len(missing) < len(R2_ENV_VARS):
        # Partially configured is almost always a deploy mistake worth shouting
        # about, rather than silently writing to a disk that gets wiped.
        print(
            "[Storage] R2 partially configured, missing: "
            + ", ".join(missing)
            + " — using local disk",
            flush=True,
        )

    return LocalStorage(media_dir)
