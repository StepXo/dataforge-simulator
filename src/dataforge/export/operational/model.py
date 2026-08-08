"""Immutable logical schema models for operational simulation datasets."""

from dataclasses import dataclass
from enum import StrEnum


class LogicalDataType(StrEnum):
    """Describe values without selecting a physical storage representation."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"


@dataclass(frozen=True, slots=True)
class ColumnDefinition:
    """Describe one logical dataset column."""

    name: str
    logical_type: LogicalDataType
    nullable: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Column name must not be empty")


@dataclass(frozen=True, slots=True)
class RelationshipDefinition:
    """Describe a logical reference between operational datasets."""

    column: str
    references_dataset: str
    references_column: str

    def __post_init__(self) -> None:
        if not self.column or not self.references_dataset or not self.references_column:
            raise ValueError("Relationship names must not be empty")


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    """Describe a logical dataset schema without containing rows."""

    name: str
    columns: tuple[ColumnDefinition, ...]
    primary_key: tuple[str, ...]
    relationships: tuple[RelationshipDefinition, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Dataset name must not be empty")
        column_names = tuple(column.name for column in self.columns)
        if len(column_names) != len(set(column_names)):
            raise ValueError(f"Dataset contains duplicate columns: {self.name}")
        if any(column not in column_names for column in self.primary_key):
            raise ValueError(
                f"Dataset primary key references unknown columns: {self.name}"
            )
        if any(item.column not in column_names for item in self.relationships):
            raise ValueError(
                f"Dataset relationship references an unknown local column: {self.name}"
            )

    def require_column(self, name: str) -> ColumnDefinition:
        """Return a column by name or fail clearly."""
        for column in self.columns:
            if column.name == name:
                return column
        raise KeyError(f"Unknown column in dataset {self.name}: {name}")


@dataclass(frozen=True, slots=True)
class OperationalDataModel:
    """Group and validate the complete operational dataset schema."""

    datasets: tuple[DatasetDefinition, ...]

    def __post_init__(self) -> None:
        names = tuple(dataset.name for dataset in self.datasets)
        if len(names) != len(set(names)):
            raise ValueError("Operational data model contains duplicate datasets")
        datasets = {dataset.name: dataset for dataset in self.datasets}
        for dataset in self.datasets:
            for relationship in dataset.relationships:
                referenced = datasets.get(relationship.references_dataset)
                if referenced is None:
                    raise ValueError(
                        "Relationship references an unknown dataset: "
                        f"{relationship.references_dataset}"
                    )
                if relationship.references_column not in {
                    column.name for column in referenced.columns
                }:
                    raise ValueError(
                        "Relationship references an unknown column: "
                        f"{relationship.references_dataset}."
                        f"{relationship.references_column}"
                    )

    def require_dataset(self, name: str) -> DatasetDefinition:
        """Return a dataset by name or fail clearly."""
        for dataset in self.datasets:
            if dataset.name == name:
                return dataset
        raise KeyError(f"Unknown operational dataset: {name}")
