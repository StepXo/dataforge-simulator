"""Tests for synchronous in-memory event publication."""

from unittest.mock import Mock

from dataforge.events.event import DomainEvent
from dataforge.events.event_bus import EventBus
from dataforge.events.event_store import EventStore


def test_publish_stores_event_before_calling_registered_handler() -> None:
    store = EventStore()
    bus = EventBus(store)
    event = DomainEvent(event_type="SomethingHappened", payload={})

    def assert_event_is_already_stored(received: DomainEvent) -> None:
        assert store.all_events() == [received]

    handler = Mock(side_effect=assert_event_is_already_stored)
    bus.subscribe("SomethingHappened", handler)

    bus.publish(event)

    handler.assert_called_once_with(event)
    assert store.all_events() == [event]


def test_two_handlers_receive_the_same_event() -> None:
    bus = EventBus(EventStore())
    event = DomainEvent(event_type="SomethingHappened", payload={})
    first_handler = Mock()
    second_handler = Mock()
    bus.subscribe("SomethingHappened", first_handler)
    bus.subscribe("SomethingHappened", second_handler)

    bus.publish(event)

    first_handler.assert_called_once_with(event)
    second_handler.assert_called_once_with(event)


def test_publish_without_handlers_stores_event_without_failing() -> None:
    store = EventStore()
    bus = EventBus(store)
    event = DomainEvent(event_type="SomethingHappened", payload={})

    bus.publish(event)

    assert store.all_events() == [event]


def test_handlers_for_other_event_types_are_not_called() -> None:
    bus = EventBus(EventStore())
    other_handler = Mock()
    bus.subscribe("OtherEvent", other_handler)

    bus.publish(DomainEvent(event_type="SomethingHappened", payload={}))

    other_handler.assert_not_called()
