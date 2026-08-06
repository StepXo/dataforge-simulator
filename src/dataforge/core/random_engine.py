"""Deterministic random number generation."""

from collections.abc import Sequence
from random import Random


class RandomEngine:
    """Provide an isolated pseudo-random sequence for a simulation."""

    def __init__(self, seed: int) -> None:
        self._generator = Random(seed)

    def uniform(self, minimum: float, maximum: float) -> float:
        """Return the next floating-point value within the requested range."""
        return self._generator.uniform(minimum, maximum)

    def randint(self, minimum: int, maximum: int) -> int:
        """Return the next integer within an inclusive range."""
        return self._generator.randint(minimum, maximum)

    def choice[T](self, values: Sequence[T]) -> T:
        """Return one value from a non-empty sequence."""
        return self._generator.choice(values)
