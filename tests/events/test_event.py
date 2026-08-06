"""Tests for domain event definitions."""

from datetime import UTC, datetime
from uuid import UUID

from dataforge.events.event import DomainEvent, EntityCreated


def test_domain_event_generates_uuid_and_timestamp_and_preserves_payload() -> None:
    payload: dict[str, object] = {"value": 42}
    before = datetime.now(UTC)

    event = DomainEvent(event_type="SomethingHappened", payload=payload)

    assert isinstance(event.event_id, UUID)
    assert before <= event.timestamp <= datetime.now(UTC)
    assert event.payload == payload


def test_entity_created_has_expected_type_and_payload() -> None:
    event = EntityCreated(entity_id="entity-001", activity_factor=1.14)

    assert event.event_type == "EntityCreated"
    assert event.payload == {
        "entity_id": "entity-001",
        "activity_factor": 1.14,
    }
