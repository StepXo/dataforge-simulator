"""Tests for immutable operational schema contracts and validation."""

from dataclasses import FrozenInstanceError

import pytest

from dataforge.export.operational import (
    ColumnDefinition,
    DatasetDefinition,
    LogicalDataType,
    OperationalDataModel,
    RelationshipDefinition,
)


def column(name: str = "id") -> ColumnDefinition:
    return ColumnDefinition(name, LogicalDataType.STRING)


def test_schema_models_are_immutable() -> None:
    relation = RelationshipDefinition("parent_id", "parents", "id")
    dataset = DatasetDefinition(
        "items",
        (column(), column("parent_id")),
        ("id",),
        (relation,),
    )
    value = OperationalDataModel(
        (DatasetDefinition("parents", (column(),), ("id",)), dataset)
    )

    with pytest.raises(FrozenInstanceError):
        value.datasets = ()
    with pytest.raises(FrozenInstanceError):
        dataset.primary_key = ()
    with pytest.raises(FrozenInstanceError):
        relation.column = "other"
    with pytest.raises(FrozenInstanceError):
        dataset.columns[0].nullable = True


def test_dataset_rejects_duplicate_columns() -> None:
    with pytest.raises(ValueError, match="duplicate columns"):
        DatasetDefinition("items", (column(), column()), ("id",))


def test_dataset_rejects_unknown_primary_key_column() -> None:
    with pytest.raises(ValueError, match="primary key"):
        DatasetDefinition("items", (column(),), ("missing",))


def test_dataset_rejects_unknown_relationship_column() -> None:
    relation = RelationshipDefinition("missing", "parents", "id")

    with pytest.raises(ValueError, match="unknown local column"):
        DatasetDefinition("items", (column(),), ("id",), (relation,))


def test_model_rejects_duplicate_dataset_names() -> None:
    item = DatasetDefinition("items", (column(),), ("id",))

    with pytest.raises(ValueError, match="duplicate datasets"):
        OperationalDataModel((item, item))


def test_model_rejects_unknown_referenced_dataset() -> None:
    child = DatasetDefinition(
        "children",
        (column(), column("parent_id")),
        ("id",),
        (RelationshipDefinition("parent_id", "parents", "id"),),
    )

    with pytest.raises(ValueError, match="unknown dataset"):
        OperationalDataModel((child,))


def test_model_rejects_unknown_referenced_column() -> None:
    parent = DatasetDefinition("parents", (column(),), ("id",))
    child = DatasetDefinition(
        "children",
        (column(), column("parent_id")),
        ("id",),
        (RelationshipDefinition("parent_id", "parents", "missing"),),
    )

    with pytest.raises(ValueError, match="unknown column"):
        OperationalDataModel((parent, child))


def test_dataset_and_column_lookup_fail_clearly() -> None:
    item = DatasetDefinition("items", (column(),), ("id",))
    model = OperationalDataModel((item,))

    assert model.require_dataset("items") is item
    assert item.require_column("id").logical_type is LogicalDataType.STRING
    with pytest.raises(KeyError, match="Unknown operational dataset"):
        model.require_dataset("missing")
    with pytest.raises(KeyError, match="Unknown column"):
        item.require_column("missing")
