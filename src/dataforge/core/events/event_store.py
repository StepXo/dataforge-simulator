"""Temporary in-memory event storage."""

from dataforge.core.events.event import DomainEvent


class EventStore:
    """Store domain events for the lifetime of the current process."""

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    def append(self, event: DomainEvent) -> None:
        """Append an event to the store."""
        self._events.append(event)

    def all_events(self) -> list[DomainEvent]:
        """Return a snapshot of all stored events."""
        return list(self._events)

    def clear(self) -> None:
        """Remove all stored events."""
        self._events.clear()

    def count(self) -> int:
        """Return the number of stored events."""
        return len(self._events)
