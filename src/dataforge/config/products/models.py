"""Validated models for external product catalog configuration."""

from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CurrencyCode = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=3, max_length=3)
]


class CategoryDefinition(BaseModel):
    """Define one catalog category."""

    id: NonEmptyString
    name: NonEmptyString


class ProductDefinition(BaseModel):
    """Define one configured product."""

    id: NonEmptyString
    name: NonEmptyString
    category_id: NonEmptyString
    base_price: Decimal = Field(gt=0)
    base_cost: Decimal = Field(ge=0)
    active: bool = True

    @model_validator(mode="after")
    def validate_cost(self) -> Self:
        if self.base_cost >= self.base_price:
            raise ValueError("base_cost must be less than base_price")
        return self


class ProductCatalogDefinition(BaseModel):
    """Define and validate a complete product catalog."""

    currency: CurrencyCode
    categories: list[CategoryDefinition] = Field(min_length=1)
    products: list[ProductDefinition] = Field(min_length=1)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        category_ids = [category.id for category in self.categories]
        if len(category_ids) != len(set(category_ids)):
            raise ValueError("Category IDs must be unique")
        product_ids = [product.id for product in self.products]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Product IDs must be unique")
        known_categories = set(category_ids)
        for product in self.products:
            if product.category_id not in known_categories:
                raise ValueError(
                    f"Product {product.id} references unknown category "
                    f"{product.category_id}"
                )
        return self
