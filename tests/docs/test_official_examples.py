from pathlib import Path

from dataforge.config.geography.loader import load_geography
from dataforge.config.products.loader import load_product_catalog
from dataforge.runtime.runner import SimulationRunner
from dataforge.scenario.loader import load_scenario

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "examples"
GEOGRAPHY = EXAMPLES / "geography" / "colombia.yaml"
PRODUCTS = EXAMPLES / "products" / "taqueria.yaml"
SCENARIO = EXAMPLES / "scenarios" / "taqueria-colombia.yaml"


def test_official_examples_are_exactly_the_three_documented_yaml_files() -> None:
    assert sorted(path.relative_to(EXAMPLES) for path in EXAMPLES.rglob("*.yaml")) == [
        Path("geography/colombia.yaml"),
        Path("products/taqueria.yaml"),
        Path("scenarios/taqueria-colombia.yaml"),
    ]


def test_official_geography_and_product_catalog_load() -> None:
    geography = load_geography(GEOGRAPHY)
    catalog = load_product_catalog(PRODUCTS)

    assert geography.country.code == "CO"
    assert len(geography.regions) == 3
    assert len(geography.cities) == 4
    assert catalog.currency == "COP"
    assert len(catalog.categories) == 5
    assert len(catalog.products) == 12


def test_official_scenario_loads_relative_sources_and_runs() -> None:
    scenario = load_scenario(SCENARIO)

    assert scenario.geography.source == GEOGRAPHY.resolve()
    assert scenario.products.source == PRODUCTS.resolve()

    result = SimulationRunner(scenario).run()

    assert result.simulation_summary.ticks_processed == 744
    assert result.simulation_summary.engine_executions == 7440
    assert result.validation_passed is True


def test_readme_is_utf8_without_known_corruption() -> None:
    raw = (ROOT / "README.md").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")

    content = raw.decode("utf-8")
    for corrupted in ("\ufffd", "Ã", "Â", "â€", "â€™", "â€œ", "â€"):
        assert corrupted not in content
