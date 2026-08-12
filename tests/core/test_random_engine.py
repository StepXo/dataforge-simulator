"""Tests for isolated deterministic random generation."""

import pytest

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


def test_weighted_choice_is_reproducible_and_validated() -> None:
    first = RandomEngine(42)
    second = RandomEngine(42)
    values = ("a", "b", "c")
    weights = (1.0, 2.0, 3.0)
    assert [first.weighted_choice(values, weights) for _ in range(5)] == [
        second.weighted_choice(values, weights) for _ in range(5)
    ]


def test_weighted_choice_rejects_invalid_weights() -> None:
    engine = RandomEngine(42)
    with pytest.raises(ValueError, match="equal length"):
        engine.weighted_choice(("a",), ())
    with pytest.raises(ValueError, match="non-negative"):
        engine.weighted_choice(("a",), (-1.0,))
    with pytest.raises(ValueError, match="positive"):
        engine.weighted_choice(("a", "b"), (0.0, 0.0))


def test_normal_is_reproducible_and_validates_deviation() -> None:
    first = RandomEngine(42)
    second = RandomEngine(42)
    assert [first.normal(20, 4) for _ in range(5)] == [
        second.normal(20, 4) for _ in range(5)
    ]
    with pytest.raises(ValueError, match="non-negative"):
        first.normal(20, -1)
