"""Temporary in-memory event storage."""

from dataforge.core.events.event import DomainEvent


class EventStore:
    """Optionally retain domain events for the lifetime of the process."""

    def __init__(self, *, retain_events: bool = True) -> None:
        self._events: list[DomainEvent] = []
        self._retain_events = retain_events

    def append(self, event: DomainEvent) -> None:
        """Append an event when history retention is enabled."""
        if self._retain_events:
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
