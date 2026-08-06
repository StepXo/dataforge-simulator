"""Tests for product catalog validation and loading."""

from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dataforge.configuration.products import (
    CategoryDefinition,
    ProductCatalogDefinition,
    ProductDefinition,
    load_product_catalog,
)


def product(**changes: object) -> ProductDefinition:
    values: dict[str, object] = {
        "id": "product",
        "name": "Product",
        "category_id": "category",
        "base_price": Decimal("100"),
        "base_cost": Decimal("60"),
    }
    values.update(changes)
    return ProductDefinition.model_validate(values)


def catalog(**changes: object) -> ProductCatalogDefinition:
    values: dict[str, object] = {
        "currency": "cop",
        "categories": [CategoryDefinition(id="category", name="Category")],
        "products": [product()],
    }
    values.update(changes)
    return ProductCatalogDefinition.model_validate(values)


def test_valid_catalog_normalizes_currency() -> None:
    assert catalog().currency == "COP"


@pytest.mark.parametrize("currency", ["", "CO", "COPX"])
def test_invalid_currency_fails(currency: str) -> None:
    with pytest.raises(ValidationError):
        catalog(currency=currency)


@pytest.mark.parametrize(
    "changes",
    [
        {"categories": []},
        {"products": []},
        {
            "categories": [
                CategoryDefinition(id="category", name="A"),
                CategoryDefinition(id="category", name="B"),
            ]
        },
        {"products": [product(), product(name="Other")]},
        {"products": [product(category_id="missing")]},
    ],
)
def test_invalid_catalog_structure_fails(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        catalog(**changes)


@pytest.mark.parametrize(
    "price,cost",
    [("0", "0"), ("-1", "0"), ("100", "-1"), ("100", "100"), ("100", "101")],
)
def test_invalid_money_fails(price: str, cost: str) -> None:
    with pytest.raises(ValidationError):
        product(base_price=Decimal(price), base_cost=Decimal(cost))


def test_taqueria_loader(tmp_path: Path) -> None:
    loaded = load_product_catalog(Path("configs/products/taqueria.yaml"))
    assert isinstance(loaded, ProductCatalogDefinition)
    assert loaded.currency == "COP"
    assert len(loaded.categories) == 5
    assert len(loaded.products) == 20
    assert all(
        product.category_id in {category.id for category in loaded.categories}
        for product in loaded.products
    )

    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        load_product_catalog(missing)
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("products: [", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_product_catalog(invalid)
