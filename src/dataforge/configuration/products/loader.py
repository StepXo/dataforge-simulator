"""YAML loader for product catalog configuration."""

from pathlib import Path

import yaml

from dataforge.configuration.products.models import ProductCatalogDefinition


def load_product_catalog(path: Path) -> ProductCatalogDefinition:
    """Load and validate a product catalog from YAML."""
    with path.open(encoding="utf-8") as file:
        content = yaml.safe_load(file)
    return ProductCatalogDefinition.model_validate(content)
