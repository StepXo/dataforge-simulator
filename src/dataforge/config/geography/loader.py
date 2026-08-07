"""YAML loader for geography reference configuration."""

from pathlib import Path

import yaml

from dataforge.config.geography.models import GeographyDefinition


def load_geography(path: Path) -> GeographyDefinition:
    """Load and validate a geography definition from a YAML file."""
    with path.open(encoding="utf-8") as file:
        content = yaml.safe_load(file)
    return GeographyDefinition.model_validate(content)
