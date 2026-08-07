"""Tests for generic in-memory state collections."""

from dataclasses import dataclass

import pytest

from dataforge.core.state.collection import StateCollection


@dataclass(frozen=True)
class Record:
    name: str


def require_record(collection: StateCollection[Record], key: str) -> Record:
    return collection.require(key)


def test_state_collection_starts_empty_and_stores_typed_values() -> None:
    collection: StateCollection[Record] = StateCollection()
    record = Record(name="first")

    assert collection.count() == 0
    assert collection.get("missing") is None

    collection.add("record-001", record)

    assert collection.count() == 1
    assert collection.get("record-001") is record
    assert require_record(collection, "record-001") is record
    assert collection.contains("record-001") is True
    assert collection.contains("missing") is False


def test_state_collection_missing_required_or_removed_key_raises() -> None:
    collection: StateCollection[Record] = StateCollection()

    with pytest.raises(KeyError):
        collection.require("missing")
    with pytest.raises(KeyError):
        collection.remove("missing")


def test_state_collection_remove_and_clear() -> None:
    collection: StateCollection[Record] = StateCollection()
    first = Record(name="first")
    collection.add("first", first)
    collection.add("second", Record(name="second"))

    assert collection.remove("first") is first
    assert collection.contains("first") is False

    collection.clear()

    assert collection.count() == 0


def test_state_collection_all_is_safe_and_preserves_insertion_order() -> None:
    collection: StateCollection[Record] = StateCollection()
    first = Record(name="first")
    second = Record(name="second")
    collection.add("first", first)
    collection.add("second", second)

    snapshot = collection.all()

    assert snapshot == (first, second)
    assert snapshot + (Record(name="external"),) != collection.all()
    assert collection.count() == 2


def test_state_collection_rejects_duplicate_key() -> None:
    collection: StateCollection[Record] = StateCollection()
    collection.add("record", Record(name="first"))

    with pytest.raises(ValueError, match="State key already exists: record"):
        collection.add("record", Record(name="replacement"))


def test_state_collection_replace_requires_existing_key_and_preserves_order() -> None:
    collection: StateCollection[Record] = StateCollection()
    collection.add("first", Record(name="before"))
    collection.add("second", Record(name="second"))

    collection.replace("first", Record(name="after"))

    assert collection.all() == (Record(name="after"), Record(name="second"))
    with pytest.raises(KeyError):
        collection.replace("missing", Record(name="value"))
