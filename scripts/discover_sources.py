"""Throwaway live-source probe. Not part of the ingest pipeline.

Run: uv run --with holidays python scripts/discover_sources.py

Prints a JSON report to stdout. Writes nothing under data/.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from typing import Any

COM_BASE = "https://data.melbourne.vic.gov.au"
OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"
USER_AGENT = "melbourne-footfall-source-verification/0.1"
SLEEP_S = 0.35

CATALOGUE_CANDIDATES = [
    f"{COM_BASE}/api/explore/v2.1/catalog/datasets",
    f"{COM_BASE}/api/explore/v2.0/catalog/datasets",
    f"{COM_BASE}/api/v2/catalog/datasets",
    f"{COM_BASE}/api/records/1.0/search/",
    f"{COM_BASE}/api/explore/v2.1/catalog",
    f"{COM_BASE}/api/explore/v2.1/",
    f"{COM_BASE}/api/",
]

SEARCH_QUERIES = [
    "pedestrian",
    "sensor location",
    "CLUE",
    "business establishments",
    "employment",
    "jobs ANZSIC",
]


def get(url: str, timeout: int = 90) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            try:
                body: Any = json.loads(text) if text else None
            except json.JSONDecodeError:
                body = text[:4000]
            return {
                "ok": True,
                "status": resp.status,
                "url": url,
                "headers": {k: v for k, v in resp.headers.items()},
                "body": body,
                "bytes": len(raw),
            }
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")[:4000]
        return {
            "ok": False,
            "status": exc.code,
            "url": url,
            "headers": {k: v for k, v in exc.headers.items()},
            "body": err_body,
            "bytes": 0,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "url": url,
            "headers": {},
            "body": str(exc),
            "bytes": 0,
        }


def rate_headers(headers: dict[str, str]) -> dict[str, str]:
    keys = (
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "retry-after",
        "ratelimit-limit",
        "ratelimit-remaining",
    )
    found = {}
    for key, value in headers.items():
        if key.lower() in keys or "rate" in key.lower() or "limit" in key.lower():
            found[key] = value
    return found


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def probe_catalogue_versions() -> list[dict[str, Any]]:
    rows = []
    for url in CATALOGUE_CANDIDATES:
        result = get(url if "?" in url or url.endswith("/") else f"{url}?limit=1")
        time.sleep(SLEEP_S)
        body = result["body"]
        summary: Any
        if isinstance(body, dict):
            summary = {
                "keys": sorted(body.keys()),
                "total_count": body.get("total_count"),
                "links": body.get("links"),
            }
        elif isinstance(body, str):
            summary = body[:500]
        else:
            summary = body
        rows.append(
            {
                "url": result["url"],
                "ok": result["ok"],
                "status": result["status"],
                "rate_headers": rate_headers(result["headers"]),
                "summary": summary,
            }
        )
    return rows


def search_catalog(api_base: str, query: str, limit: int = 100) -> dict[str, Any]:
    where = f'search("{query}")'
    url = f"{api_base}?{urllib.parse.urlencode({'where': where, 'limit': str(limit)})}"
    result = get(url)
    time.sleep(SLEEP_S)
    hits = []
    body = result["body"]
    if result["ok"] and isinstance(body, dict):
        for row in body.get("results") or []:
            metas = (row.get("metas") or {}).get("default") or {}
            hits.append(
                {
                    "dataset_id": row.get("dataset_id"),
                    "title": metas.get("title"),
                    "records_count": metas.get("records_count"),
                    "license": metas.get("license"),
                    "keywords": metas.get("keyword"),
                }
            )
    return {
        "query": query,
        "url": result["url"],
        "ok": result["ok"],
        "status": result["status"],
        "total_count": body.get("total_count") if isinstance(body, dict) else None,
        "hits": hits,
        "error": None if result["ok"] else body,
    }


def dataset_detail(api_base: str, dataset_id: str) -> dict[str, Any]:
    url = f"{api_base}/{urllib.parse.quote(dataset_id)}"
    result = get(url)
    time.sleep(SLEEP_S)
    if not result["ok"] or not isinstance(result["body"], dict):
        return {
            "dataset_id": dataset_id,
            "ok": False,
            "status": result["status"],
            "url": result["url"],
            "error": result["body"],
        }
    body = result["body"]
    metas = (body.get("metas") or {}).get("default") or {}
    quality = (body.get("metas") or {}).get("quality") or {}
    fields = []
    for field in body.get("fields") or []:
        fields.append(
            {
                "name": field.get("name"),
                "label": field.get("label"),
                "type": field.get("type"),
                "description": field.get("description"),
            }
        )
    return {
        "dataset_id": dataset_id,
        "ok": True,
        "status": result["status"],
        "url": result["url"],
        "links": body.get("links"),
        "title": metas.get("title"),
        "description": metas.get("description"),
        "license": metas.get("license"),
        "license_url": metas.get("license_url"),
        "records_count_meta": metas.get("records_count"),
        "publisher": metas.get("publisher"),
        "timezone_meta": metas.get("timezone"),
        "data_processed": metas.get("data_processed"),
        "known_issues": quality.get("known-issues"),
        "fields": fields,
        "rate_headers": rate_headers(result["headers"]),
    }


def records_sample(api_base: str, dataset_id: str, extra: str = "") -> dict[str, Any]:
    query = extra.lstrip("&")
    suffix = f"&{query}" if query else ""
    url = f"{api_base}/{urllib.parse.quote(dataset_id)}/records?limit=5{suffix}"
    result = get(url)
    time.sleep(SLEEP_S)
    body = result["body"]
    sample = []
    returned_types: dict[str, set[str]] = defaultdict(set)
    if result["ok"] and isinstance(body, dict):
        for row in body.get("results") or []:
            sample.append(row)
            for key, value in row.items():
                returned_types[key].add(json_type(value))
    return {
        "url": result["url"],
        "ok": result["ok"],
        "status": result["status"],
        "total_count": body.get("total_count") if isinstance(body, dict) else None,
        "returned_json_types": {k: sorted(v) for k, v in returned_types.items()},
        "sample": sample,
        "error": None if result["ok"] else body,
        "rate_headers": rate_headers(result["headers"]),
    }


def extreme_record(
    api_base: str,
    dataset_id: str,
    field: str,
    descending: bool,
) -> dict[str, Any]:
    direction = "DESC" if descending else "ASC"
    url = (
        f"{api_base}/{urllib.parse.quote(dataset_id)}/records"
        f"?select={urllib.parse.quote(field)}"
        f"&order_by={urllib.parse.quote(field)}%20{direction}&limit=1"
    )
    result = get(url)
    time.sleep(SLEEP_S)
    value = None
    body = result["body"]
    if result["ok"] and isinstance(body, dict):
        rows = body.get("results") or []
        if rows:
            value = rows[0].get(field)
    return {
        "url": result["url"],
        "ok": result["ok"],
        "status": result["status"],
        "field": field,
        "descending": descending,
        "value": value,
        "error": None if result["ok"] else body,
    }


def export_formats(api_base: str, dataset_id: str) -> dict[str, Any]:
    url = f"{api_base}/{urllib.parse.quote(dataset_id)}/exports"
    result = get(url)
    time.sleep(SLEEP_S)
    return {
        "url": result["url"],
        "ok": result["ok"],
        "status": result["status"],
        "body": result["body"]
        if not result["ok"] or isinstance(result["body"], dict)
        else str(result["body"])[:1000],
        "links": result["body"].get("links")
        if isinstance(result["body"], dict)
        else None,
    }


def export_json(api_base: str, dataset_id: str, where: str) -> dict[str, Any]:
    url = (
        f"{api_base}/{urllib.parse.quote(dataset_id)}/exports/json"
        f"?where={urllib.parse.quote(where)}"
    )
    result = get(url, timeout=180)
    time.sleep(SLEEP_S)
    rows = result["body"] if isinstance(result["body"], list) else None
    return {
        "url": result["url"],
        "ok": result["ok"] and rows is not None,
        "status": result["status"],
        "bytes": result["bytes"],
        "n_rows": len(rows) if rows is not None else None,
        "rows": rows,
        "error": None if rows is not None else result["body"],
        "rate_headers": rate_headers(result["headers"]),
    }


def analyse_counts_month(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n_rows": 0}
    columns = sorted(rows[0].keys())
    sensor_keys = [
        c
        for c in columns
        if c.lower() in {"location_id", "sensor_id"}
        or ("sensor" in c.lower() and "id" in c.lower())
    ]
    count_keys = [
        c
        for c in columns
        if c.lower()
        in {"pedestriancount", "total_of_directions", "hourly_counts", "count"}
    ]
    time_keys = [
        c
        for c in columns
        if c.lower() in {"sensing_date", "date_time", "timestamp", "datetime", "time"}
        or "date" in c.lower()
        or "time" in c.lower()
    ]
    sensor_key = sensor_keys[0] if sensor_keys else None
    count_key = count_keys[0] if count_keys else None
    time_key = time_keys[0] if time_keys else None

    sensors = set()
    zeros = 0
    null_counts = 0
    count_types: Counter[str] = Counter()
    time_types: Counter[str] = Counter()
    time_examples: list[Any] = []
    pairs: Counter[tuple[Any, Any]] = Counter()
    field_nulls = Counter()
    sensors_676869: dict[str, int] = {"67": 0, "68": 0, "69": 0}

    for row in rows:
        for key, value in row.items():
            if value is None:
                field_nulls[key] += 1
        if sensor_key:
            sid = row.get(sensor_key)
            sensors.add(sid)
            if str(sid) in sensors_676869:
                sensors_676869[str(sid)] += 1
        if count_key:
            value = row.get(count_key)
            count_types[json_type(value)] += 1
            if value is None:
                null_counts += 1
            elif value == 0 or value == 0.0 or value == "0":
                zeros += 1
        if time_key:
            value = row.get(time_key)
            time_types[json_type(value)] += 1
            if len(time_examples) < 8:
                time_examples.append(value)
        hour = row.get("hourday")
        if sensor_key and time_key:
            pairs[(row.get(sensor_key), row.get(time_key), hour)] += 1

    dupes = [
        {"sensor": s, "timestamp": t, "hourday": h, "n": n}
        for (s, t, h), n in pairs.items()
        if n > 1
    ]
    dupes_676869 = [d for d in dupes if str(d["sensor"]) in {"67", "68", "69"}]
    return {
        "n_rows": len(rows),
        "columns": columns,
        "sensor_key_used": sensor_key,
        "count_key_used": count_key,
        "time_key_used": time_key,
        "distinct_sensor_ids": len(sensors),
        "sensor_id_examples": sorted(sensors, key=lambda x: (str(type(x)), str(x)))[
            :20
        ],
        "zero_count_rows": zeros,
        "null_count_rows": null_counts,
        "count_json_types": dict(count_types),
        "time_json_types": dict(time_types),
        "time_examples": time_examples,
        "duplicate_sensor_timestamp_rows": len(dupes),
        "duplicate_examples": dupes[:10],
        "sensors_67_68_69_row_counts": sensors_676869,
        "sensors_67_68_69_duplicate_groups": dupes_676869[:20],
        "nulls_by_field": dict(field_nulls),
        "other_fields": [
            c for c in columns if c not in {sensor_key, count_key, time_key}
        ],
    }


def probe_sensors_676869(
    api_base: str, dataset_id: str, sensor_field: str, time_field: str
) -> dict[str, Any]:
    where = f"{sensor_field} in (67, 68, 69)"
    grouped = (
        f"{api_base}/{urllib.parse.quote(dataset_id)}/records"
        f"?select={urllib.parse.quote(sensor_field)},"
        f"{urllib.parse.quote(time_field)},hourday,count(*)%20as%20n"
        f"&where={urllib.parse.quote(where)}"
        f"&group_by={urllib.parse.quote(sensor_field)},"
        f"{urllib.parse.quote(time_field)},hourday"
        f"&order_by=n%20DESC&limit=20"
    )
    counts = (
        f"{api_base}/{urllib.parse.quote(dataset_id)}/records"
        f"?select={urllib.parse.quote(sensor_field)},count(*)%20as%20n"
        f"&where={urllib.parse.quote(where)}"
        f"&group_by={urllib.parse.quote(sensor_field)}&limit=10"
    )
    grouped_res = get(grouped)
    time.sleep(SLEEP_S)
    counts_res = get(counts)
    time.sleep(SLEEP_S)
    return {
        "grouped_url": grouped_res["url"],
        "grouped_ok": grouped_res["ok"],
        "grouped_status": grouped_res["status"],
        "grouped_body": grouped_res["body"]
        if grouped_res["ok"]
        else grouped_res["body"],
        "per_sensor_url": counts_res["url"],
        "per_sensor_ok": counts_res["ok"],
        "per_sensor_body": counts_res["body"]
        if counts_res["ok"]
        else counts_res["body"],
    }


def pick_date_field(fields: list[dict[str, Any]]) -> str | None:
    names = [f["name"] for f in fields if f.get("name")]
    preferred = [
        "sensing_date",
        "date_time",
        "datetime",
        "timestamp",
        "observation_time",
        "census_year",
        "year",
    ]
    for name in preferred:
        if name in names:
            return name
    for field in fields:
        if field.get("type") in {"datetime", "date"}:
            return field["name"]
    return None


def probe_open_meteo() -> dict[str, Any]:
    hourly = "temperature_2m,precipitation,rain,wind_speed_10m,cloud_cover"
    common = {
        "latitude": "-37.8136",
        "longitude": "144.9631",
        "timezone": "Australia/Melbourne",
        "hourly": hourly,
    }

    def archive_url(start: str, end: str) -> str:
        params = {**common, "start_date": start, "end_date": end}
        return f"{OPEN_METEO}?{urllib.parse.urlencode(params)}"

    probes = {
        "recent_day": archive_url("2024-01-01", "2024-01-02"),
        "year_1940": archive_url("1940-01-01", "1940-01-02"),
        "year_1939": archive_url("1939-12-31", "1939-12-31"),
        "year_1800": archive_url("1800-01-01", "1800-01-02"),
        "far_future": archive_url("2099-01-01", "2099-01-02"),
    }
    results = {}
    for name, url in probes.items():
        result = get(url, timeout=120)
        time.sleep(SLEEP_S)
        body = result["body"]
        hourly_keys = None
        first_time = None
        last_time = None
        n_hours = None
        if isinstance(body, dict):
            hourly_block = body.get("hourly") or {}
            hourly_keys = list(hourly_block.keys())
            times = hourly_block.get("time") or []
            n_hours = len(times)
            first_time = times[0] if times else None
            last_time = times[-1] if times else None
        results[name] = {
            "url": result["url"],
            "ok": result["ok"],
            "status": result["status"],
            "rate_headers": rate_headers(result["headers"]),
            "header_keys": sorted(result["headers"].keys()),
            "top_level_keys": sorted(body.keys()) if isinstance(body, dict) else None,
            "hourly_keys": hourly_keys,
            "n_hours": n_hours,
            "first_time": first_time,
            "last_time": last_time,
            "utc_offset_seconds": body.get("utc_offset_seconds")
            if isinstance(body, dict)
            else None,
            "timezone": body.get("timezone") if isinstance(body, dict) else None,
            "timezone_abbreviation": body.get("timezone_abbreviation")
            if isinstance(body, dict)
            else None,
            "reason": body.get("reason") if isinstance(body, dict) else None,
            "error": body.get("error") if isinstance(body, dict) else None,
            "sample_hourly": (
                {
                    k: (v[:3] if isinstance(v, list) else v)
                    for k, v in (body.get("hourly") or {}).items()
                }
                if isinstance(body, dict)
                else None
            ),
            "raw_if_not_dict": None if isinstance(body, dict) else body,
        }

    docs = get("https://open-meteo.com/en/docs/historical-weather-api", timeout=60)
    docs_text = docs["body"] if isinstance(docs["body"], str) else ""
    licence_mentions = []
    for needle in ("CC BY", "API key", "api key", "1940", "rate", "10,000", "10000"):
        idx = docs_text.lower().find(needle.lower()) if docs_text else -1
        if idx >= 0:
            licence_mentions.append(
                {"needle": needle, "excerpt": docs_text[max(0, idx - 80) : idx + 120]}
            )
    results["docs_page"] = {
        "url": docs["url"],
        "ok": docs["ok"],
        "status": docs["status"],
        "excerpts": licence_mentions,
    }
    return results


def probe_holidays() -> dict[str, Any]:
    try:
        import holidays
    except ImportError as exc:
        return {"ok": False, "error": f"holidays package not installed: {exc}"}

    years = list(range(2019, 2027))
    vic = holidays.country_holidays("AU", subdiv="VIC", years=years)
    federal = holidays.country_holidays("AU", years=years)
    nsw = holidays.country_holidays("AU", subdiv="NSW", years=years)

    vic_only_vs_federal = sorted(
        {(d.isoformat(), name) for d, name in vic.items() if d not in federal}
    )
    vic_only_vs_nsw = sorted(
        {(d.isoformat(), name) for d, name in vic.items() if d not in nsw}
    )
    names_by_year: dict[int, list[str]] = {}
    for year in years:
        names_by_year[year] = sorted(
            {name for d, name in vic.items() if d.year == year}
        )

    sample_2024 = sorted(
        ((d.isoformat(), name) for d, name in vic.items() if d.year == 2024),
        key=lambda item: item[0],
    )
    return {
        "ok": True,
        "package_version": getattr(holidays, "__version__", None),
        "constructor": "holidays.country_holidays('AU', subdiv='VIC', years=2019-2026)",
        "mapping_type": type(vic).__name__,
        "key_type": type(next(iter(vic))).__name__ if vic else None,
        "value_type": type(next(iter(vic.values()))).__name__ if vic else None,
        "n_days_2019_2026": len(vic),
        "sample_2024": sample_2024,
        "names_by_year": names_by_year,
        "present_in_vic_not_federal_base": vic_only_vs_federal,
        "present_in_vic_not_nsw": vic_only_vs_nsw,
        "today_is_holiday": date.today() in vic,
    }


def main() -> int:
    report: dict[str, Any] = {
        "probed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    report["catalogue_probes"] = probe_catalogue_versions()
    working = [r for r in report["catalogue_probes"] if r["ok"] and r["status"] == 200]
    v21 = next(
        (r for r in working if "/api/explore/v2.1/catalog/datasets" in r["url"]),
        None,
    )
    api_base = f"{COM_BASE}/api/explore/v2.1/catalog/datasets"
    report["chosen_catalogue"] = {
        "api_base": api_base,
        "v2_1_worked": v21 is not None,
        "working_urls": [r["url"] for r in working],
    }

    report["catalogue_searches"] = [search_catalog(api_base, q) for q in SEARCH_QUERIES]

    wanted_ids = {
        "pedestrian-counting-system-monthly-counts-per-hour",
        "pedestrian-counting-system-sensor-locations",
    }
    found_ids: set[str] = set()
    for search in report["catalogue_searches"]:
        for hit in search["hits"]:
            if hit["dataset_id"]:
                found_ids.add(hit["dataset_id"])

    clue_candidates = sorted(
        i
        for i in found_ids
        if any(
            token in i
            for token in (
                "clue",
                "business",
                "establishment",
                "employment",
                "jobs",
                "anzsic",
                "block",
            )
        )
    )
    pedestrian_candidates = sorted(
        i for i in found_ids if "pedestrian" in i or "sensor" in i
    )
    report["candidate_ids"] = {
        "from_searches_pedestrian_or_sensor": pedestrian_candidates,
        "from_searches_clue_like": clue_candidates,
        "explicit_wanted_present": {i: i in found_ids for i in sorted(wanted_ids)},
    }

    inspect_ids = []
    for dataset_id in [
        "pedestrian-counting-system-monthly-counts-per-hour",
        "pedestrian-counting-system-sensor-locations",
        "business-establishments-with-address-and-industry-classification",
        "business-establishment-trading-name-and-industry-classification",
        "cafes-and-restaurants-with-seating-capacity",
    ]:
        inspect_ids.append(dataset_id)
    inspect_ids.extend(clue_candidates)
    # de-dupe, keep order
    seen: set[str] = set()
    ordered = []
    for dataset_id in inspect_ids:
        if dataset_id not in seen:
            seen.add(dataset_id)
            ordered.append(dataset_id)

    details = []
    for dataset_id in ordered:
        detail = dataset_detail(api_base, dataset_id)
        if not detail["ok"]:
            details.append(detail)
            continue
        sample = records_sample(api_base, dataset_id)
        detail["records"] = {k: v for k, v in sample.items() if k != "sample"}
        detail["sample_records"] = sample["sample"]
        date_field = pick_date_field(detail["fields"])
        detail["date_field_used"] = date_field
        if date_field:
            lo = extreme_record(api_base, dataset_id, date_field, descending=False)
            hi = extreme_record(api_base, dataset_id, date_field, descending=True)
            detail["min_date"] = {
                "field": date_field,
                "value": lo["value"],
                "url": lo["url"],
                "ok": lo["ok"],
            }
            detail["max_date"] = {
                "field": date_field,
                "value": hi["value"],
                "url": hi["url"],
                "ok": hi["ok"],
            }
        detail["export_formats"] = export_formats(api_base, dataset_id)
        details.append(detail)
    report["datasets"] = details

    counts = next(
        (
            d
            for d in details
            if d.get("dataset_id")
            == "pedestrian-counting-system-monthly-counts-per-hour"
            and d.get("ok")
        ),
        None,
    )
    locations = next(
        (
            d
            for d in details
            if d.get("dataset_id") == "pedestrian-counting-system-sensor-locations"
            and d.get("ok")
        ),
        None,
    )

    report["pedestrian_month_sample"] = None
    report["sensors_67_68_69"] = None
    if counts:
        time_field = counts.get("date_field_used") or "sensing_date"
        max_val = (counts.get("max_date") or {}).get("value")
        month_start = "2024-03-01"
        month_end = "2024-04-01"
        if isinstance(max_val, str) and len(max_val) >= 10:
            year, month, day = int(max_val[:4]), int(max_val[5:7]), int(max_val[8:10])
            # Use the previous calendar month when the latest day is not month-end.
            if day < 28:
                if month == 1:
                    year, month = year - 1, 12
                else:
                    month -= 1
            month_start = f"{year:04d}-{month:02d}-01"
            if month == 12:
                month_end = f"{year + 1:04d}-01-01"
            else:
                month_end = f"{year:04d}-{month + 1:02d}-01"
        where = f"{time_field} >= '{month_start}' AND {time_field} < '{month_end}'"
        exported = export_json(api_base, counts["dataset_id"], where)
        analysis = (
            analyse_counts_month(exported.pop("rows") or []) if exported["ok"] else None
        )
        report["pedestrian_month_sample"] = {
            "where": where,
            "month_start": month_start,
            "month_end_exclusive": month_end,
            **exported,
            "analysis": analysis,
        }
        sensor_field = (analysis or {}).get("sensor_key_used") or "sensor_id"
        report["sensors_67_68_69"] = probe_sensors_676869(
            api_base, counts["dataset_id"], sensor_field, time_field
        )

    if locations:
        loc_fields = [f["name"] for f in locations.get("fields") or []]
        report["sensor_location_date_like_fields"] = [
            f
            for f in loc_fields
            if any(
                token in (f or "").lower()
                for token in ("install", "removal", "reloc", "date", "status", "note")
            )
        ]

    report["open_meteo"] = probe_open_meteo()
    report["holidays"] = probe_holidays()

    json.dump(report, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
