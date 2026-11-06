"""[Member 1] DagsHub object storage for daily data and monitoring reports.

Every DagsHub repo has a bucket named after the repo. It speaks the S3 protocol, so boto3 is the
client, but nothing here is AWS: the endpoint is DagsHub's and the credentials are your DagsHub
token (used as both access key and secret).

Settings come from .env: DAGSHUB_REPO_OWNER, DAGSHUB_REPO, DAGSHUB_TOKEN.
Key prefixes (daily/, monitoring/) come from params.yaml -> storage. Versioned datasets
(data/raw, data/processed) are NOT stored here: DVC pushes those to the same DagsHub repo.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import boto3

from solarcast.config import env, params

log = logging.getLogger(__name__)

ENDPOINT = "https://dagshub.com/api/v1/repo-buckets/s3/{owner}"


def _settings() -> dict[str, str]:
    return {
        "owner": env("DAGSHUB_REPO_OWNER") or "",
        "repo": env("DAGSHUB_REPO") or "",
        "token": env("DAGSHUB_TOKEN") or "",
    }


def is_configured() -> bool:
    """True once .env has real DagsHub values (not missing and not <placeholders>)."""
    return all(v and "<" not in v for v in _settings().values())


@lru_cache
def client():
    s = _settings()
    if not is_configured():
        raise RuntimeError("DagsHub storage not configured - set DAGSHUB_* values in .env")
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT.format(owner=s["owner"]),
        aws_access_key_id=s["token"],  # boto3's parameter names; values are the DagsHub token
        aws_secret_access_key=s["token"],
        region_name="us-east-1",  # required by boto3, ignored by DagsHub
    )


def bucket() -> str:
    return _settings()["repo"]


def key(area: str, name: str) -> str:
    """Object key in one of the areas from params.yaml, e.g. key("daily", "recent/site.parquet")."""
    return f"{params()['storage'][area]}{name}"


def upload(local_path: Path, object_key: str) -> str:
    client().upload_file(str(local_path), bucket(), object_key)
    return f"dagshub://{_settings()['owner']}/{bucket()}/{object_key}"


def download(object_key: str, local_path: Path) -> Path:
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client().download_file(bucket(), object_key, str(local_path))
    return local_path


def maybe_upload(local_path: Path, object_key: str) -> str | None:
    """Upload if DagsHub is configured; otherwise log and continue (local-only mode)."""
    if not is_configured():
        log.info("storage not configured - kept %s local only", local_path)
        return None
    return upload(local_path, object_key)


def list_keys(prefix: str = "") -> list[str]:
    paginator = client().get_paginator("list_objects_v2")
    return [
        obj["Key"]
        for page in paginator.paginate(Bucket=bucket(), Prefix=prefix)
        for obj in page.get("Contents", [])
    ]
