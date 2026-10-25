"""Private object storage for attachments. Keys are server-generated (never user-controlled paths)."""

import os
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import get_settings

ALLOWED: dict[str, tuple[str, list[bytes]]] = {
    # extension: (content type, magic-byte prefixes)
    ".pdf": ("application/pdf", [b"%PDF-"]),
    ".png": ("image/png", [b"\x89PNG\r\n\x1a\n"]),
    ".jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".webp": ("image/webp", [b"RIFF"]),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", [b"PK\x03\x04"]),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", [b"PK\x03\x04"]),
    ".dwg": ("application/acad", [b"AC10"]),
    ".dxf": ("application/dxf", []),  # text
    ".csv": ("text/csv", []),
    ".txt": ("text/plain", []),
}


class UploadRejected(Exception):
    pass


def sniff(filename: str, head: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise UploadRejected(f"File type {ext or '(none)'} is not allowed")
    ctype, magics = ALLOWED[ext]
    if magics and not any(head.startswith(m) for m in magics):
        raise UploadRejected("File content does not match its extension")
    if ext == ".webp" and head[8:12] != b"WEBP":
        raise UploadRejected("File content does not match its extension")
    if not magics:  # text types: must be UTF-8 without NUL bytes, and must not look like HTML/script
        if b"\x00" in head:
            raise UploadRejected("Binary content in a text file")
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            try:
                head[:-3].decode("utf-8")
            except UnicodeDecodeError as e:
                raise UploadRejected("Text files must be UTF-8") from e
        lowered = head[:2048].lower()
        if b"<script" in lowered or b"<html" in lowered:
            raise UploadRejected("Markup content is not allowed")
    return ctype


def safe_filename(name: str) -> str:
    base = os.path.basename(name).replace("\x00", "")
    keep = "".join(c for c in base if c.isalnum() or c in "._- ()")
    return (keep or "file")[:200]


class Storage(Protocol):
    def put(self, key: str, data: BinaryIO, content_type: str) -> None: ...
    def open(self, key: str) -> BinaryIO: ...
    def signed_url(self, key: str, filename: str) -> str | None: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError("invalid key")
        return p

    def put(self, key: str, data: BinaryIO, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            while chunk := data.read(1024 * 1024):
                f.write(chunk)

    def open(self, key: str) -> BinaryIO:
        return open(self._path(key), "rb")

    def signed_url(self, key: str, filename: str) -> str | None:
        return None  # streamed through the authenticated API instead

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.ttl = s.signed_url_seconds
        self.client = boto3.client("s3", region_name=s.s3_region, endpoint_url=s.s3_endpoint_url)

    def put(self, key: str, data: BinaryIO, content_type: str) -> None:
        self.client.upload_fileobj(data, self.bucket, key, ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"})

    def open(self, key: str) -> BinaryIO:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def signed_url(self, key: str, filename: str) -> str | None:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key, "ResponseContentDisposition": f'attachment; filename="{filename}"'},
            ExpiresIn=self.ttl,
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3Storage() if s.storage_backend == "s3" else LocalStorage(s.storage_local_path)
    return _storage


def new_key(plant_id: uuid.UUID, ext: str) -> str:
    return f"plants/{plant_id}/{uuid.uuid4().hex}{ext}"
