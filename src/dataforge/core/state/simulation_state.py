"""Shared in-memory state for one simulation execution."""

from dataforge.core.state.collection import StateCollection


class SimulationState:
    """Manage named state collections in creation order."""

    def __init__(self) -> None:
        self._collections: dict[str, StateCollection[object]] = {}

    def create_collection(self, name: str) -> StateCollection[object]:
        """Create an empty collection with an exact, validated name."""
        if not name or name != name.strip():
            raise ValueError("Collection name must be non-empty without outer spaces")
        if name in self._collections:
            raise ValueError(f"State collection already exists: {name}")

        collection: StateCollection[object] = StateCollection()
        self._collections[name] = collection
        return collection

    def has_collection(self, name: str) -> bool:
        """Return whether a named collection exists."""
        return name in self._collections

    def collection(self, name: str) -> StateCollection[object]:
        """Return a collection, raising KeyError when absent."""
        return self._collections[name]

    def collection_names(self) -> tuple[str, ...]:
        """Return an immutable snapshot of names in creation order."""
        return tuple(self._collections)

    def clear(self) -> None:
        """Clear every collection and remove them from the state."""
        for collection in self._collections.values():
            collection.clear()
        self._collections.clear()

    def evict_tick(
        self,
        tick_index: int,
        collection_names: tuple[str, ...],
    ) -> None:
        """Remove one completed tick from explicitly named collections."""
        key = f"tick-{tick_index}"
        for name in collection_names:
            collection = self._collections.get(name)
            if collection is not None and collection.contains(key):
                collection.remove(key)

    @property
    def total_records(self) -> int:
        """Return the total number of records across all collections."""
        return sum(collection.count() for collection in self._collections.values())


def require_tick_context[T](
    state: SimulationState,
    collection_name: str,
    tick_index: int,
    expected_type: type[T],
    *,
    owner: str,
) -> T:
    """Return a typed context for one tick from a required collection."""
    if not state.has_collection(collection_name):
        raise ValueError(f"Required {owner} collection is missing: {collection_name}")
    value = state.collection(collection_name).get(f"tick-{tick_index}")
    if not isinstance(value, expected_type):
        raise ValueError(f"{collection_name} context is missing for tick: {tick_index}")
    return value
