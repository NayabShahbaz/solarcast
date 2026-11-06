"""Shared HTTP session with retries for all public data APIs."""

from __future__ import annotations

import logging
from functools import lru_cache

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from solarcast.config import params

log = logging.getLogger(__name__)


class SourceError(RuntimeError):
    """A data source returned an error or unusable data. Message says which source and why."""


@lru_cache
def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = "solarcast-mlops/0.1 (university project)"
    return s


def get_json(source: str, url: str, query: dict) -> dict:
    timeout = params()["sources"]["request_timeout_s"]
    log.info("GET %s %s", source, {k: v for k, v in query.items() if k != "apikey"})
    try:
        r = session().get(url, params=query, timeout=timeout)
    except requests.RequestException as e:
        raise SourceError(f"{source}: request failed: {e}") from e
    if r.status_code != 200:
        raise SourceError(f"{source}: HTTP {r.status_code}: {r.text[:300]}")
    return r.json()
