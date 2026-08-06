"""Tests for the base domain entity."""

from datetime import UTC, datetime
from uuid import UUID

from dataforge.core.entity import Entity


def test_entity_generates_uuid_and_creation_date() -> None:
    before = datetime.now(UTC)

    entity = Entity()

    assert isinstance(entity.id, UUID)
    assert before <= entity.created_at <= datetime.now(UTC)


def test_entity_preserves_metadata() -> None:
    metadata: dict[str, object] = {"source": "test", "priority": 1}

    entity = Entity(metadata=metadata)

    assert entity.metadata == metadata


def test_entity_metadata_is_optional() -> None:
    assert Entity().metadata == {}
