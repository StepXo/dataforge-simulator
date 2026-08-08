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
