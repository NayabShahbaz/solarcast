"""[Member 1] S3 helpers. Bucket and prefixes come from .env (bucket created by Member 3)."""

from pathlib import Path


def upload(local_path: Path, key: str) -> str:
    raise NotImplementedError


def download(key: str, local_path: Path) -> Path:
    raise NotImplementedError
