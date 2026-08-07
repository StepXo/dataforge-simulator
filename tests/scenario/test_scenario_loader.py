"""Tests for typed scenario configuration and path resolution."""

from datetime import datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dataforge.core.tick import TickUnit
from dataforge.customers.generator import CustomerGenerationConfig
from dataforge.engines.demand.engine import DemandEngineConfig
from dataforge.engines.replenishment.engine import ReplenishmentEngineConfig
from dataforge.geography.generator import LocationGenerationConfig
from dataforge.inventory.generator import InventoryGenerationConfig
from dataforge.promotions.generator import PromotionGenerationConfig
from dataforge.scenario import ScenarioDefinition, load_scenario

PROJECT_ROOT = Path(__file__).parents[2]
EXAMPLE_SCENARIO = PROJECT_ROOT / "configs/scenarios/taqueria-colombia.yaml"


def valid_scenario(geography: str, products: str) -> dict[str, object]:
    return {
        "simulation": {
            "seed": 42,
            "start_datetime": "2026-01-01T00:00:00",
            "end_datetime": "2026-01-02T00:00:00",
            "tick_unit": "hour",
        },
        "geography": {"source": geography},
        "products": {"source": products},
        "locations": {},
        "customers": {},
        "inventory": {},
        "promotions": {},
        "demand": {},
        "replenishment": {},
    }


def write_scenario(path: Path, content: object) -> None:
    path.write_text(yaml.safe_dump(content), encoding="utf-8")


def referenced_scenario(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "geography.yaml").write_text("country: {}", encoding="utf-8")
    (sources / "products.yaml").write_text("products: []", encoding="utf-8")
    scenario_directory = tmp_path / "scenarios"
    scenario_directory.mkdir()
    path = scenario_directory / "scenario.yaml"
    content = valid_scenario("../sources/geography.yaml", "../sources/products.yaml")
    return path, content


def test_example_scenario_loads_with_reused_configs() -> None:
    scenario = load_scenario(EXAMPLE_SCENARIO)
    assert isinstance(scenario, ScenarioDefinition)
    assert scenario.simulation.seed == 42
    assert scenario.simulation.start_datetime == datetime(2024, 1, 1)
    assert scenario.simulation.end_datetime == datetime(2026, 12, 31, 23)
    assert scenario.simulation.tick_unit is TickUnit.HOUR
    assert (
        scenario.geography.source
        == (PROJECT_ROOT / "configs/geography/colombia.yaml").resolve()
    )
    assert (
        scenario.products.source
        == (PROJECT_ROOT / "configs/products/taqueria.yaml").resolve()
    )
    assert isinstance(scenario.locations, LocationGenerationConfig)
    assert isinstance(scenario.customers, CustomerGenerationConfig)
    assert isinstance(scenario.inventory, InventoryGenerationConfig)
    assert isinstance(scenario.promotions, PromotionGenerationConfig)
    assert isinstance(scenario.demand, DemandEngineConfig)
    assert isinstance(scenario.replenishment, ReplenishmentEngineConfig)


@pytest.mark.parametrize(
    ("field", "value"),
    [("end_datetime", "2026-01-01T00:00:00"), ("tick_unit", "minute")],
)
def test_invalid_simulation_definition_fails(
    tmp_path: Path, field: str, value: str
) -> None:
    path, content = referenced_scenario(tmp_path)
    simulation = content["simulation"]
    assert isinstance(simulation, dict)
    simulation[field] = value
    write_scenario(path, content)
    with pytest.raises(ValidationError):
        load_scenario(path)


@pytest.mark.parametrize("source_section", ["geography", "products"])
def test_missing_referenced_source_fails(tmp_path: Path, source_section: str) -> None:
    path, content = referenced_scenario(tmp_path)
    content[source_section] = {"source": "missing.yaml"}
    write_scenario(path, content)
    with pytest.raises(FileNotFoundError, match="Scenario source file does not exist"):
        load_scenario(path)


def test_invalid_yaml_and_invalid_structure_fail(tmp_path: Path) -> None:
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("simulation: [", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_scenario(invalid_yaml)

    invalid_structure = tmp_path / "structure.yaml"
    write_scenario(invalid_structure, {"simulation": {}})
    with pytest.raises(ValidationError):
        load_scenario(invalid_structure)


def test_nested_config_validation_is_reused(tmp_path: Path) -> None:
    path, content = referenced_scenario(tmp_path)
    content["inventory"] = {"min_initial_stock": 10, "max_initial_stock": 5}
    write_scenario(path, content)
    with pytest.raises(ValidationError, match="max_initial_stock"):
        load_scenario(path)


def test_sources_resolve_relative_to_scenario_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, content = referenced_scenario(tmp_path)
    write_scenario(path, content)
    unrelated_directory = tmp_path / "unrelated"
    unrelated_directory.mkdir()
    monkeypatch.chdir(unrelated_directory)
    scenario = load_scenario(path)
    assert scenario.geography.source == (tmp_path / "sources/geography.yaml").resolve()
    assert scenario.products.source == (tmp_path / "sources/products.yaml").resolve()


def test_scenario_and_owned_models_are_immutable() -> None:
    scenario = load_scenario(EXAMPLE_SCENARIO)
    with pytest.raises(ValidationError):
        scenario.simulation.seed = 1
    with pytest.raises(ValidationError):
        scenario.geography.source = Path("other.yaml")
    with pytest.raises(ValidationError):
        scenario.products.source = Path("other.yaml")
    with pytest.raises(ValidationError):
        scenario.simulation = scenario.simulation


def test_arbitrary_source_filenames_are_accepted(tmp_path: Path) -> None:
    (tmp_path / "foo.yaml").write_text("country: arbitrary", encoding="utf-8")
    (tmp_path / "bar.yaml").write_text("catalog: arbitrary", encoding="utf-8")
    scenario_path = tmp_path / "scenario.yaml"
    write_scenario(scenario_path, valid_scenario("./foo.yaml", "./bar.yaml"))

    scenario = load_scenario(scenario_path)

    assert scenario.geography.source == (tmp_path / "foo.yaml").resolve()
    assert scenario.products.source == (tmp_path / "bar.yaml").resolve()


def test_country_and_business_names_have_no_semantics(tmp_path: Path) -> None:
    (tmp_path / "mexico.yaml").write_text(
        "country: {code: ZZ, name: Arbitrary}", encoding="utf-8"
    )
    (tmp_path / "farmacia.yaml").write_text(
        "business_type: unrelated", encoding="utf-8"
    )
    scenario_path = tmp_path / "scenario.yaml"
    write_scenario(scenario_path, valid_scenario("mexico.yaml", "farmacia.yaml"))

    scenario = load_scenario(scenario_path)

    assert scenario.geography.source.name == "mexico.yaml"
    assert scenario.products.source.name == "farmacia.yaml"


def test_sources_support_arbitrary_nested_directories(tmp_path: Path) -> None:
    scenario_directory = tmp_path / "fixtures/scenarios"
    geography = tmp_path / "fixtures/custom/geos/anything.yaml"
    products = tmp_path / "fixtures/business/catalogs/whatever.yaml"
    scenario_directory.mkdir(parents=True)
    geography.parent.mkdir(parents=True)
    products.parent.mkdir(parents=True)
    geography.write_text("not-inspected: geography", encoding="utf-8")
    products.write_text("not-inspected: products", encoding="utf-8")
    scenario_path = scenario_directory / "runtime.yaml"
    write_scenario(
        scenario_path,
        valid_scenario(
            "../custom/geos/anything.yaml",
            "../business/catalogs/whatever.yaml",
        ),
    )

    scenario = load_scenario(scenario_path)

    assert scenario.geography.source == geography.resolve()
    assert scenario.products.source == products.resolve()
