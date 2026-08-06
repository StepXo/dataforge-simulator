"""Tests for deterministic preview generation."""

from datetime import date
from decimal import Decimal

from dataforge.simulation.models import SimulationPreviewConfig
from dataforge.simulation.preview_service import SimulationPreviewService


def make_config(*, seed: int = 42, entity_count: int = 5) -> SimulationPreviewConfig:
    return SimulationPreviewConfig(
        seed=seed,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        entity_count=entity_count,
    )


def test_generates_requested_number_with_sequential_ids() -> None:
    result = SimulationPreviewService().generate(make_config(entity_count=1000))

    assert len(result.entities) == 1000
    assert result.entities[0].id == "entity-001"
    assert result.entities[1].id == "entity-002"
    assert result.entities[-1].id == "entity-1000"


def test_period_days_include_both_dates() -> None:
    result = SimulationPreviewService().generate(make_config())

    assert result.period.days == 7


def test_same_configuration_produces_identical_result() -> None:
    service = SimulationPreviewService()

    assert service.generate(make_config()) == service.generate(make_config())


def test_different_seed_changes_generated_entities() -> None:
    service = SimulationPreviewService()

    assert (
        service.generate(make_config(seed=42)).entities
        != service.generate(make_config(seed=43)).entities
    )


def test_activity_factors_are_in_range_and_have_at_most_two_decimals() -> None:
    result = SimulationPreviewService().generate(make_config(entity_count=1000))

    assert all(0.50 <= entity.activity_factor <= 1.50 for entity in result.entities)
    assert all(
        Decimal(str(entity.activity_factor)).as_tuple().exponent >= -2
        for entity in result.entities
    )
