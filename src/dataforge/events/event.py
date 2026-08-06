"""Domain event definitions."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Describe something that occurred in the domain."""

    event_type: str
    payload: dict[str, object]
    event_id: UUID = field(default_factory=uuid4, init=False)
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC),
        init=False,
    )


class EntityCreated(DomainEvent):
    """Record the creation of one generic simulated entity."""

    def __init__(self, entity_id: str, activity_factor: float) -> None:
        super().__init__(
            event_type="EntityCreated",
            payload={
                "entity_id": entity_id,
                "activity_factor": activity_factor,
            },
        )
