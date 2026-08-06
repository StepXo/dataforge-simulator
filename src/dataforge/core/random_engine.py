"""Deterministic random number generation."""

from random import Random


class RandomEngine:
    """Provide an isolated pseudo-random sequence for a simulation."""

    def __init__(self, seed: int) -> None:
        self._generator = Random(seed)

    def uniform(self, minimum: float, maximum: float) -> float:
        """Return the next floating-point value within the requested range."""
        return self._generator.uniform(minimum, maximum)
