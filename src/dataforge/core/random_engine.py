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

    def normal(self, mean: float, standard_deviation: float) -> float:
        """Return the next normally distributed value."""
        if standard_deviation < 0:
            raise ValueError("standard_deviation must be non-negative")
        return self._generator.gauss(mean, standard_deviation)

    def choice[T](self, values: Sequence[T]) -> T:
        """Return one value from a non-empty sequence."""
        return self._generator.choice(values)

    def weighted_choice[T](self, values: Sequence[T], weights: Sequence[float]) -> T:
        """Select one value using non-negative relative weights."""
        if not values or len(values) != len(weights):
            raise ValueError(
                "Values and weights must be non-empty and have equal length"
            )
        if any(weight < 0 for weight in weights):
            raise ValueError("Weights must be non-negative")
        total = sum(weights)
        if total <= 0:
            raise ValueError("At least one weight must be positive")

        threshold = self._generator.random() * total
        cumulative = 0.0
        for value, weight in zip(values, weights, strict=True):
            cumulative += weight
            if threshold < cumulative:
                return value
        return values[-1]
