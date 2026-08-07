"""Product catalog configuration loading."""

from dataforge.config.products.loader import load_product_catalog
from dataforge.config.products.models import (
    CategoryDefinition,
    ProductCatalogDefinition,
    ProductDefinition,
)

__all__ = [
    "CategoryDefinition",
    "ProductCatalogDefinition",
    "ProductDefinition",
    "load_product_catalog",
]
