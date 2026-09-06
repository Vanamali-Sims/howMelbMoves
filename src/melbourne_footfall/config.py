"""Load and validate config/sources.yml.

Sources stay unverified until a later step confirms them against the live API.
This module must not invent endpoints, dataset ids, or column names.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class DateRange(BaseModel):
    """Optional inclusive date bounds for a source extract."""

    model_config = ConfigDict(extra="forbid")

    start: date | None = None
    end: date | None = None


class Source(BaseModel):
    """One external dataset. Treat as untrusted until verified is True."""

    model_config = ConfigDict(extra="forbid")

    name: str
    base_url: str
    dataset_id: str
    expected_columns: set[str]
    date_range: DateRange | None = None
    verified: bool = False


class SourcesConfig(BaseModel):
    """Root document for config/sources.yml."""

    model_config = ConfigDict(extra="forbid")

    sources: list[Source] = Field(default_factory=list)


def project_root(start: Path | None = None) -> Path:
    """Walk parents until pyproject.toml and config/ are found."""
    here = (start or Path(__file__)).resolve()
    if here.is_file():
        here = here.parent
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "config").is_dir():
            return candidate
    msg = "Could not locate project root (pyproject.toml + config/)"
    raise FileNotFoundError(msg)


def default_sources_path() -> Path:
    return project_root() / "config" / "sources.yml"


def get_source(name: str, config: SourcesConfig | None = None) -> Source:
    """Return a named source. Raises if missing or not verified."""
    cfg = config if config is not None else load_sources_config()
    for source in cfg.sources:
        if source.name == name:
            if not source.verified:
                msg = f"source {name!r} is not verified"
                raise ValueError(msg)
            return source
    msg = f"unknown source {name!r}"
    raise KeyError(msg)


def load_sources_config(path: Path | None = None) -> SourcesConfig:
    """Read YAML and validate. An empty or missing file yields no sources."""
    config_path = path if path is not None else default_sources_path()
    if not config_path.exists() or config_path.stat().st_size == 0:
        return SourcesConfig()

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw is None:
        return SourcesConfig()
    return SourcesConfig.model_validate(raw)
