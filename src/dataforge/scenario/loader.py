"""Loader for complete simulation scenario configuration."""

from pathlib import Path

import yaml

from dataforge.scenario.models import ScenarioDefinition


def load_scenario(path: Path) -> ScenarioDefinition:
    """Load a scenario and resolve its source paths relative to the YAML file."""
    scenario_path = path.resolve()
    with scenario_path.open(encoding="utf-8") as file:
        content = yaml.safe_load(file)

    scenario = ScenarioDefinition.model_validate(content)
    base_directory = scenario_path.parent
    geography_source = _resolve_source(base_directory, scenario.geography.source)
    product_source = _resolve_source(base_directory, scenario.products.source)
    return scenario.model_copy(
        update={
            "geography": scenario.geography.model_copy(
                update={"source": geography_source}
            ),
            "products": scenario.products.model_copy(update={"source": product_source}),
        }
    )


def _resolve_source(base_directory: Path, source: Path) -> Path:
    resolved = source if source.is_absolute() else base_directory / source
    resolved = resolved.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Scenario source file does not exist: {resolved}")
    return resolved
