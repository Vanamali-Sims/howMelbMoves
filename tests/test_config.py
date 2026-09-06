from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from melbourne_footfall.config import (
    SourcesConfig,
    default_sources_path,
    load_sources_config,
    project_root,
)


def test_empty_file_returns_no_sources(tmp_path: Path) -> None:
    path = tmp_path / "sources.yml"
    path.write_text("", encoding="utf-8")
    config = load_sources_config(path)
    assert config.sources == []


def test_comment_only_file_returns_no_sources(tmp_path: Path) -> None:
    path = tmp_path / "sources.yml"
    path.write_text("# no sources yet\n", encoding="utf-8")
    config = load_sources_config(path)
    assert config.sources == []


def test_missing_file_returns_no_sources(tmp_path: Path) -> None:
    config = load_sources_config(tmp_path / "does-not-exist.yml")
    assert config.sources == []


def test_empty_sources_list(tmp_path: Path) -> None:
    path = tmp_path / "sources.yml"
    path.write_text("sources: []\n", encoding="utf-8")
    config = load_sources_config(path)
    assert config == SourcesConfig(sources=[])


def test_valid_source_defaults_verified_false(tmp_path: Path) -> None:
    path = tmp_path / "sources.yml"
    path.write_text(
        "\n".join(
            [
                "sources:",
                "  - name: example",
                "    base_url: https://example.invalid",
                "    dataset_id: not-a-real-id",
                "    expected_columns:",
                "      - sensor_id",
                "      - observation_time",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_sources_config(path)

    assert len(config.sources) == 1
    source = config.sources[0]
    assert source.name == "example"
    assert source.verified is False
    assert source.date_range is None
    assert source.expected_columns == {"sensor_id", "observation_time"}


def test_optional_date_range(tmp_path: Path) -> None:
    path = tmp_path / "sources.yml"
    path.write_text(
        "\n".join(
            [
                "sources:",
                "  - name: example",
                "    base_url: https://example.invalid",
                "    dataset_id: not-a-real-id",
                "    expected_columns: [sensor_id]",
                "    date_range:",
                "      start: 2019-01-01",
                "      end: 2024-12-31",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    source = load_sources_config(path).sources[0]
    assert source.date_range is not None
    assert source.date_range.start == date(2019, 1, 1)
    assert source.date_range.end == date(2024, 12, 31)


def test_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "sources.yml"
    path.write_text(
        "\n".join(
            [
                "sources:",
                "  - name: example",
                "    base_url: https://example.invalid",
                "    dataset_id: not-a-real-id",
                "    expected_columns: [sensor_id]",
                "    invented_field: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_sources_config(path)


def test_repo_sources_yml_loads() -> None:
    config = load_sources_config()
    assert isinstance(config, SourcesConfig)
    assert config.sources == []
    assert default_sources_path() == project_root() / "config" / "sources.yml"
    assert default_sources_path().is_file()
