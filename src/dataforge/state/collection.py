"""Generic ordered collection for simulation state."""


class StateCollection[T]:
    """Store typed values by unique string keys in insertion order."""

    def __init__(self) -> None:
        self._values: dict[str, T] = {}

    def add(self, key: str, value: T) -> None:
        """Add a value, rejecting duplicate keys."""
        if key in self._values:
            raise ValueError(f"State key already exists: {key}")
        self._values[key] = value

    def get(self, key: str) -> T | None:
        """Return a value or None when its key is absent."""
        return self._values.get(key)

    def require(self, key: str) -> T:
        """Return a value, raising KeyError when its key is absent."""
        return self._values[key]

    def contains(self, key: str) -> bool:
        """Return whether a key exists."""
        return key in self._values

    def remove(self, key: str) -> T:
        """Remove and return a value, raising KeyError when absent."""
        return self._values.pop(key)

    def all(self) -> tuple[T, ...]:
        """Return an immutable snapshot in insertion order."""
        return tuple(self._values.values())

    def count(self) -> int:
        """Return the number of stored values."""
        return len(self._values)

    def clear(self) -> None:
        """Remove all stored values."""
        self._values.clear()
