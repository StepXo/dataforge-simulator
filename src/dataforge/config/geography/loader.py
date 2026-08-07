"""YAML loader for geography reference configuration."""

from pathlib import Path

from dataforge.config.geography.models import GeographyDefinition
from dataforge.config.loader import load_yaml


def load_geography(path: Path) -> GeographyDefinition:
    """Load and validate a geography definition from a YAML file."""
    return GeographyDefinition.model_validate(load_yaml(path))
