"""Shared technical loading for external YAML configuration."""

from pathlib import Path

import yaml


def load_yaml(path: Path) -> object:
    """Load one YAML document without assigning domain semantics."""
    with path.open(encoding="utf-8") as file:
        content: object = yaml.safe_load(file)
    return content
