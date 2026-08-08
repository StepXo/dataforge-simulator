"""Structural and semantic tests for the DataForge operational schema."""

import ast
import inspect
from pathlib import Path

import dataforge.export.operational as operational
from dataforge.export.operational import LogicalDataType, build_operational_data_model

EXPECTED_DATASETS = {
    "countries",
    "regions",
    "administrative_areas",
    "cities",
    "locations",
    "categories",
    "products",
    "customers",
    "promotions",
    "promotion_targets",
    "transactions",
    "transaction_lines",
    "transaction_line_promotions",
    "inventory",
    "inventory_movements",
    "replenishments",
    "metrics",
}


def column_names(dataset_name: str) -> set[str]:
    dataset = build_operational_data_model().require_dataset(dataset_name)
    return {column.name for column in dataset.columns}


def relationship_targets(dataset_name: str) -> set[tuple[str, str, str]]:
    dataset = build_operational_data_model().require_dataset(dataset_name)
    return {
        (item.column, item.references_dataset, item.references_column)
        for item in dataset.relationships
    }


def test_operational_schema_contains_current_domain_datasets() -> None:
    model = build_operational_data_model()

    assert {dataset.name for dataset in model.datasets} == EXPECTED_DATASETS
    assert "run_summary" not in EXPECTED_DATASETS


def test_all_dataset_names_columns_keys_and_relationships_are_valid() -> None:
    model = build_operational_data_model()
    names = [dataset.name for dataset in model.datasets]

    assert len(names) == len(set(names))
    for dataset in model.datasets:
        columns = [column.name for column in dataset.columns]
        assert len(columns) == len(set(columns))
        assert set(dataset.primary_key) <= set(columns)
        for relationship in dataset.relationships:
            assert relationship.column in columns
            referenced = model.require_dataset(relationship.references_dataset)
            assert relationship.references_column in {
                column.name for column in referenced.columns
            }


def test_geography_product_and_customer_relationships_are_explicit() -> None:
    assert ("country_id", "countries", "country_id") in relationship_targets("regions")
    assert ("city_id", "cities", "city_id") in relationship_targets("locations")
    assert ("category_id", "categories", "category_id") in relationship_targets(
        "products"
    )
    assert ("home_city_id", "cities", "city_id") in relationship_targets("customers")
    assert (
        "preferred_location_id",
        "locations",
        "location_id",
    ) in relationship_targets("customers")


def test_transactions_are_baskets_and_lines_are_products() -> None:
    transactions = column_names("transactions")
    lines = column_names("transaction_lines")

    assert {"transaction_id", "basket_id", "customer_id", "location_id"} <= transactions
    assert "product_id" not in transactions
    assert {"transaction_line_id", "transaction_id", "product_id", "quantity"} <= lines
    assert (
        "transaction_id",
        "transactions",
        "transaction_id",
    ) in relationship_targets("transaction_lines")
    assert ("product_id", "products", "product_id") in relationship_targets(
        "transaction_lines"
    )


def test_repeated_promotion_ids_use_bridge_datasets() -> None:
    assert "target_ids" not in column_names("promotions")
    assert column_names("promotion_targets") == {"promotion_id", "target_id"}
    assert "applied_promotion_ids" not in column_names("transaction_lines")
    assert column_names("transaction_line_promotions") == {
        "transaction_line_id",
        "promotion_id",
    }


def test_inventory_snapshot_and_historical_movements_remain_distinct() -> None:
    inventory = build_operational_data_model().require_dataset("inventory")
    movements = build_operational_data_model().require_dataset("inventory_movements")

    assert inventory.primary_key == ("inventory_id",)
    assert {"current_stock", "reorder_point", "max_stock"} <= column_names("inventory")
    assert {"stock_before", "stock_after", "occurred_at", "movement_type"} <= (
        column_names("inventory_movements")
    )
    assert "occurred_at" not in column_names("inventory")
    assert movements.require_column("transaction_id").nullable is True
    assert movements.require_column("basket_id").nullable is True


def test_metrics_are_per_tick_and_money_is_logical_decimal() -> None:
    model = build_operational_data_model()
    metrics = model.require_dataset("metrics")
    products = model.require_dataset("products")
    transactions = model.require_dataset("transactions")

    assert metrics.primary_key == ("tick_index",)
    assert (
        metrics.require_column("current_time").logical_type is LogicalDataType.DATETIME
    )
    for dataset, names in (
        (products, ("base_price", "base_cost", "base_margin")),
        (
            transactions,
            ("gross_amount", "discount_amount", "net_amount", "lost_sales_amount"),
        ),
        (
            metrics,
            (
                "gross_sales_amount",
                "discount_amount",
                "net_sales_amount",
                "lost_sales_amount",
            ),
        ),
    ):
        assert all(
            dataset.require_column(name).logical_type is LogicalDataType.DECIMAL
            for name in names
        )


def test_operational_module_has_no_physical_export_imports() -> None:
    package_path = Path(inspect.getfile(operational)).parent
    forbidden = {
        "csv",
        "pyarrow",
        "pandas",
        "sqlalchemy",
        "sqlite3",
        "duckdb",
        "psycopg",
        "postgres",
    }
    imported_roots: set[str] = set()
    for path in package_path.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])

    assert imported_roots.isdisjoint(forbidden)


def test_operational_schema_contains_no_business_fixture_terms() -> None:
    model = build_operational_data_model()
    schema_terms = {dataset.name for dataset in model.datasets} | {
        column.name for dataset in model.datasets for column in dataset.columns
    }

    assert schema_terms.isdisjoint({"taqueria", "tacos", "farmacia", "supermercado"})
