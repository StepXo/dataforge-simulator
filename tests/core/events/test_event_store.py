"""Tests for temporary in-memory event storage."""

from dataforge.core.events.event import DomainEvent
from dataforge.core.events.event_store import EventStore


def test_append_count_all_events_and_clear() -> None:
    store = EventStore()
    first = DomainEvent(event_type="First", payload={})
    second = DomainEvent(event_type="Second", payload={})

    store.append(first)
    store.append(second)

    assert store.count() == 2
    assert store.all_events() == [first, second]

    store.clear()

    assert store.count() == 0
    assert store.all_events() == []


def test_all_events_returns_a_snapshot() -> None:
    store = EventStore()
    store.append(DomainEvent(event_type="SomethingHappened", payload={}))

    events = store.all_events()
    events.clear()

    assert store.count() == 1


def test_event_store_can_disable_history_retention() -> None:
    store = EventStore(retain_events=False)
    event = DomainEvent(event_type="NoHistory", payload={})

    store.append(event)

    assert store.count() == 0
    assert store.all_events() == []
