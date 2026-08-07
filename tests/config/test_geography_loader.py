"""Tests for loading geography configuration from YAML."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dataforge.config.geography import GeographyDefinition, load_geography

PROJECT_ROOT = Path(__file__).parents[2]
COLOMBIA_CONFIG = PROJECT_ROOT / "configs" / "geography" / "colombia.yaml"


def test_geography_loader_loads_colombia_example() -> None:
    geography = load_geography(COLOMBIA_CONFIG)

    assert isinstance(geography, GeographyDefinition)
    assert geography.country.code == "CO"
    assert len(geography.regions) == 3
    assert len(geography.administrative_areas) == 5
    assert len(geography.cities) == 5
    assert geography.cities[0].name == "Medell\u00edn"


def test_geography_loader_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_geography(tmp_path / "missing.yaml")


def test_geography_loader_invalid_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("country: [unclosed", encoding="utf-8")

    with pytest.raises(yaml.YAMLError):
        load_geography(path)


def test_geography_loader_invalid_structure_raises(tmp_path: Path) -> None:
    path = tmp_path / "invalid-structure.yaml"
    path.write_text("country:\n  code: C\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_geography(path)
