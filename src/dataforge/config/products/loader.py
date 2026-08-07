"""YAML loader for product catalog configuration."""

from pathlib import Path

from dataforge.config.loader import load_yaml
from dataforge.config.products.models import ProductCatalogDefinition


def load_product_catalog(path: Path) -> ProductCatalogDefinition:
    """Load and validate a product catalog from YAML."""
    return ProductCatalogDefinition.model_validate(load_yaml(path))
