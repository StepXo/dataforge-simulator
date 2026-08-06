"""Results returned by bootstrap execution."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BootstrapRunSummary:
    """Summarize changes made by one bootstrap run."""

    generators_executed: int
    collections_created: int
    records_created: int
