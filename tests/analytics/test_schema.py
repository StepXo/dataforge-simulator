"""Contracts for the initial dimensional analytical model."""

from dataforge.analytics import AnalyticalDatasetKind, build_analytical_model
from dataforge.export.operational.model import LogicalDataType


def test_analytical_model_defines_approved_grains_and_keys() -> None:
    model = build_analytical_model()

    assert {item.name for item in model.datasets} == {
        "dim_date",
        "dim_customer",
        "dim_product",
        "dim_location",
        "dim_promotion",
        "fact_sales",
        "fact_inventory_movement",
        "fact_replenishment",
        "bridge_sales_promotion",
    }
    sales = model.require_dataset("fact_sales")
    movement = model.require_dataset("fact_inventory_movement")
    replenishment = model.require_dataset("fact_replenishment")
    assert sales.grain == "one transaction-line outcome"
    assert sales.primary_key == ("transaction_line_id",)
    assert movement.grain == "one inventory movement"
    assert movement.primary_key == ("movement_id",)
    assert replenishment.grain == "one replenishment request lifecycle"
    assert replenishment.primary_key == ("replenishment_id",)
    assert all(
        item.kind is AnalyticalDatasetKind.DIMENSION
        for item in model.datasets
        if item.name.startswith("dim_")
    )


def test_money_is_decimal_and_nullable_completion_is_explicit() -> None:
    model = build_analytical_model()
    sales = model.require_dataset("fact_sales")
    for name in (
        "unit_price",
        "gross_sales_amount",
        "discount_amount",
        "net_sales_amount",
        "lost_sales_amount",
    ):
        assert sales.require_column(name).logical_type is LogicalDataType.DECIMAL
    replenishment = model.require_dataset("fact_replenishment")
    for name in ("received_quantity", "completed_tick_index", "completed_at"):
        assert replenishment.require_column(name).nullable


def test_bridge_contains_no_commercial_measures() -> None:
    bridge = build_analytical_model().require_dataset("bridge_sales_promotion")
    assert bridge.primary_key == ("transaction_line_id", "promotion_id")
    assert {column.name for column in bridge.columns} == {
        "transaction_line_id",
        "promotion_id",
    }
