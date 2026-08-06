"""Tests for isolated deterministic random generation."""

from dataforge.core.random_engine import RandomEngine


def generate_sequence(engine: RandomEngine) -> list[float]:
    return [engine.uniform(0.50, 1.50) for _ in range(10)]


def test_same_seed_produces_same_sequence() -> None:
    assert generate_sequence(RandomEngine(42)) == generate_sequence(RandomEngine(42))


def test_different_seeds_produce_different_sequences() -> None:
    assert generate_sequence(RandomEngine(42)) != generate_sequence(RandomEngine(43))


def test_uniform_values_respect_requested_range() -> None:
    values = generate_sequence(RandomEngine(42))

    assert all(0.50 <= value <= 1.50 for value in values)
