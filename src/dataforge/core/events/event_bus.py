"""Synchronous in-memory domain event publication."""

from collections import defaultdict
from collections.abc import Callable

from dataforge.core.events.event import DomainEvent
from dataforge.core.events.event_store import EventStore

EventHandler = Callable[[DomainEvent], None]


class EventBus:
    """Store events and synchronously notify matching handlers."""

    def __init__(self, event_store: EventStore) -> None:
        self._event_store = event_store
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        """Store an event before notifying all matching handlers."""
        self._event_store.append(event)
        for handler in self._handlers[event.event_type]:
            handler(event)
