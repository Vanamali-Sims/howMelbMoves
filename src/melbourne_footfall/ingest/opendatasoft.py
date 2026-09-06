"""Generic City of Melbourne Explore API client.

Only the v2.1 catalogue and export paths recorded in
docs/source_verification.md are used:

  GET {base}/api/explore/v2.1/catalog/datasets/{dataset_id}
  GET {base}/api/explore/v2.1/catalog/datasets/{dataset_id}/records
  GET {base}/api/explore/v2.1/catalog/datasets/{dataset_id}/exports/{format}

Records: limit max 100, offset+limit < 10000.
Portal headers advertised X-RateLimit-Limit: 10000 per day.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger("melbourne_footfall.ingest")

CATALOG_PREFIX = "/api/explore/v2.1/catalog/datasets"
RECORDS_LIMIT = 100
RECORDS_OFFSET_CAP = 10000
DEFAULT_MIN_INTERVAL_S = 0.2
USER_AGENT = "melbourne-footfall-ingest/0.1"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class OpenDataSoftError(RuntimeError):
    pass


class OpenDataSoftClient:
    def __init__(
        self,
        base_url: str,
        *,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        max_retries: int = 5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_interval_s = min_interval_s
        self.max_retries = max_retries
        self._last_request_at = 0.0
        self.rate_limit_remaining: int | None = None

    def catalog_url(self, dataset_id: str | None = None) -> str:
        root = f"{self.base_url}{CATALOG_PREFIX}"
        if dataset_id is None:
            return root
        return f"{root}/{urllib.parse.quote(dataset_id)}"

    def dataset_meta(self, dataset_id: str) -> dict[str, Any]:
        body = self._get_json(self.catalog_url(dataset_id))
        if not isinstance(body, dict):
            msg = f"catalogue lookup for {dataset_id} did not return an object"
            raise OpenDataSoftError(msg)
        return body

    def export_json(
        self, dataset_id: str, where: str | None = None
    ) -> list[dict[str, Any]]:
        url = f"{self.catalog_url(dataset_id)}/exports/json"
        if where:
            url = f"{url}?where={urllib.parse.quote(where)}"
        body = self._get_json(url, timeout=300)
        if not isinstance(body, list):
            msg = f"export/json for {dataset_id} did not return an array"
            raise OpenDataSoftError(msg)
        return body

    def export_bytes(
        self, dataset_id: str, fmt: str, where: str | None = None
    ) -> bytes:
        url = f"{self.catalog_url(dataset_id)}/exports/{fmt}"
        if where:
            url = f"{url}?where={urllib.parse.quote(where)}"
        return self._get_bytes(url, timeout=300)

    def iterate_records(
        self,
        dataset_id: str,
        *,
        where: str | None = None,
        page_size: int = RECORDS_LIMIT,
    ) -> list[dict[str, Any]]:
        """Paginate /records. Stops before offset+limit exceeds 10000."""
        if page_size > RECORDS_LIMIT:
            page_size = RECORDS_LIMIT
        rows: list[dict[str, Any]] = []
        offset = 0
        while offset + page_size <= RECORDS_OFFSET_CAP:
            query = f"limit={page_size}&offset={offset}"
            if where:
                query = f"{query}&where={urllib.parse.quote(where)}"
            url = f"{self.catalog_url(dataset_id)}/records?{query}"
            body = self._get_json(url)
            if not isinstance(body, dict):
                msg = f"records for {dataset_id} did not return an object"
                raise OpenDataSoftError(msg)
            batch = body.get("results") or []
            rows.extend(batch)
            total = body.get("total_count")
            if len(batch) < page_size:
                break
            if total is not None and len(rows) >= int(total):
                break
            offset += page_size
        return rows

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)

    def _get_json(self, url: str, timeout: int = 90) -> Any:
        raw = self._get_bytes(url, timeout=timeout)
        return json.loads(raw.decode("utf-8"))

    def _get_bytes(self, url: str, timeout: int = 90) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    self._last_request_at = time.monotonic()
                    remaining = resp.headers.get("X-RateLimit-Remaining")
                    if remaining is not None:
                        self.rate_limit_remaining = int(remaining)
                    return resp.read()
            except urllib.error.HTTPError as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
                if exc.code not in RETRY_STATUSES:
                    detail = exc.read().decode("utf-8", errors="replace")[:500]
                    msg = f"HTTP {exc.code} for {url}: {detail}"
                    raise OpenDataSoftError(msg) from exc
                retry_after = exc.headers.get("Retry-After")
                wait = (
                    float(retry_after)
                    if retry_after
                    else (2**attempt) + random.random()
                )
                logger.warning(
                    "retry attempt=%s status=%s wait=%.1fs url=%s",
                    attempt + 1,
                    exc.code,
                    wait,
                    url,
                )
                time.sleep(wait)
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                wait = (2**attempt) + random.random()
                logger.warning(
                    "retry attempt=%s error=%s wait=%.1fs url=%s",
                    attempt + 1,
                    exc,
                    wait,
                    url,
                )
                time.sleep(wait)
        msg = f"failed after {self.max_retries} retries: {url}"
        raise OpenDataSoftError(msg) from last_error
