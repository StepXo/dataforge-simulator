"""Tests for geography configuration models and relationships."""

import pytest
from pydantic import ValidationError

from dataforge.configuration.geography import (
    AdministrativeAreaDefinition,
    CityDefinition,
    CountryDefinition,
    GeographyDefinition,
    RegionDefinition,
)


def valid_geography_data() -> dict[str, object]:
    return {
        "country": {"code": "CO", "name": "Colombia"},
        "regions": [{"id": "andean", "name": "Andean"}],
        "administrative_areas": [
            {
                "id": "antioquia",
                "name": "Antioquia",
                "type": "department",
                "region_id": "andean",
            }
        ],
        "cities": [
            {
                "id": "medellin",
                "name": "Medellin",
                "administrative_area_id": "antioquia",
            }
        ],
    }


def test_geography_country_is_valid_and_normalizes_code() -> None:
    country = CountryDefinition(code="co", name="Colombia")

    assert country.code == "CO"
    assert country.name == "Colombia"


@pytest.mark.parametrize("code", ["C", "COL", ""])
def test_geography_country_rejects_invalid_code_length(code: str) -> None:
    with pytest.raises(ValidationError):
        CountryDefinition(code=code, name="Colombia")


def test_geography_region_rejects_empty_value() -> None:
    with pytest.raises(ValidationError):
        RegionDefinition(id="andean", name="   ")


def test_geography_administrative_area_rejects_empty_value() -> None:
    with pytest.raises(ValidationError):
        AdministrativeAreaDefinition(
            id="antioquia",
            name="Antioquia",
            type="",
            region_id="andean",
        )


def test_geography_city_rejects_empty_value() -> None:
    with pytest.raises(ValidationError):
        CityDefinition(
            id="medellin",
            name="",
            administrative_area_id="antioquia",
        )


def test_geography_rejects_duplicate_region_id() -> None:
    data = valid_geography_data()
    data["regions"] = [
        {"id": "andean", "name": "First"},
        {"id": "andean", "name": "Second"},
    ]

    with pytest.raises(ValidationError, match="Region IDs must be unique"):
        GeographyDefinition.model_validate(data)


def test_geography_rejects_duplicate_administrative_area_id() -> None:
    data = valid_geography_data()
    data["administrative_areas"] = [
        {
            "id": "antioquia",
            "name": "First",
            "type": "department",
            "region_id": "andean",
        },
        {
            "id": "antioquia",
            "name": "Second",
            "type": "department",
            "region_id": "andean",
        },
    ]

    with pytest.raises(ValidationError, match="Administrative area IDs must be unique"):
        GeographyDefinition.model_validate(data)


def test_geography_rejects_duplicate_city_id() -> None:
    data = valid_geography_data()
    data["cities"] = [
        {
            "id": "medellin",
            "name": "First",
            "administrative_area_id": "antioquia",
        },
        {
            "id": "medellin",
            "name": "Second",
            "administrative_area_id": "antioquia",
        },
    ]

    with pytest.raises(ValidationError, match="City IDs must be unique"):
        GeographyDefinition.model_validate(data)


def test_geography_rejects_unknown_region_reference() -> None:
    data = valid_geography_data()
    data["administrative_areas"] = [
        {
            "id": "antioquia",
            "name": "Antioquia",
            "type": "department",
            "region_id": "missing",
        }
    ]

    with pytest.raises(ValidationError, match="references unknown region missing"):
        GeographyDefinition.model_validate(data)


def test_geography_rejects_unknown_administrative_area_reference() -> None:
    data = valid_geography_data()
    data["cities"] = [
        {
            "id": "medellin",
            "name": "Medellin",
            "administrative_area_id": "missing",
        }
    ]

    with pytest.raises(
        ValidationError,
        match="references unknown administrative area missing",
    ):
        GeographyDefinition.model_validate(data)
