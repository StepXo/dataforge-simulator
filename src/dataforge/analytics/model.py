"""Format-independent contracts for analytical datasets and records."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from dataforge.export.operational.model import LogicalDataType
from dataforge.export.operational.sink import OperationalValue


class AnalyticalDatasetKind(StrEnum):
    DIMENSION = "dimension"
    FACT = "fact"
    BRIDGE = "bridge"


@dataclass(frozen=True, slots=True)
class AnalyticalColumnDefinition:
    name: str
    logical_type: LogicalDataType
    nullable: bool = False


@dataclass(frozen=True, slots=True)
class AnalyticalRelationshipDefinition:
    column: str
    references_dataset: str
    references_column: str


@dataclass(frozen=True, slots=True)
class AnalyticalDatasetDefinition:
    """Define one typed analytical dataset and its documented grain."""

    name: str
    kind: AnalyticalDatasetKind
    grain: str
    sources: tuple[str, ...]
    columns: tuple[AnalyticalColumnDefinition, ...]
    primary_key: tuple[str, ...]
    relationships: tuple[AnalyticalRelationshipDefinition, ...] = ()

    def __post_init__(self) -> None:
        names = tuple(column.name for column in self.columns)
        if not self.name or not self.grain or not self.sources:
            raise ValueError("Analytical dataset metadata must not be empty")
        if len(names) != len(set(names)):
            raise ValueError(f"Analytical dataset has duplicate columns: {self.name}")
        if any(name not in names for name in self.primary_key):
            raise ValueError(f"Analytical primary key is invalid: {self.name}")
        if any(item.column not in names for item in self.relationships):
            raise ValueError(f"Analytical relationship is invalid: {self.name}")

    def require_column(self, name: str) -> AnalyticalColumnDefinition:
        for column in self.columns:
            if column.name == name:
                return column
        raise KeyError(f"Unknown analytical column in {self.name}: {name}")


@dataclass(frozen=True, slots=True)
class AnalyticalModel:
    datasets: tuple[AnalyticalDatasetDefinition, ...]

    def __post_init__(self) -> None:
        names = tuple(dataset.name for dataset in self.datasets)
        if len(names) != len(set(names)):
            raise ValueError("Analytical model contains duplicate datasets")
        by_name = {dataset.name: dataset for dataset in self.datasets}
        for dataset in self.datasets:
            for relationship in dataset.relationships:
                target = by_name.get(relationship.references_dataset)
                if target is None:
                    raise ValueError("Analytical relationship target is unknown")
                target.require_column(relationship.references_column)

    def require_dataset(self, name: str) -> AnalyticalDatasetDefinition:
        for dataset in self.datasets:
            if dataset.name == name:
                return dataset
        raise KeyError(f"Unknown analytical dataset: {name}")


@dataclass(frozen=True, slots=True)
class AnalyticalRecord:
    dataset: str
    values: Mapping[str, OperationalValue]
