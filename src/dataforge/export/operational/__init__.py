"""Public contracts for the format-independent operational data model."""

from dataforge.export.operational.builder import OperationalDataBuilder
from dataforge.export.operational.model import (
    ColumnDefinition,
    DatasetDefinition,
    LogicalDataType,
    OperationalDataModel,
    RelationshipDefinition,
)
from dataforge.export.operational.schema import build_operational_data_model
from dataforge.export.operational.sink import (
    NullOperationalDataSink,
    OperationalDataSink,
    OperationalRecord,
)

__all__ = [
    "ColumnDefinition",
    "DatasetDefinition",
    "LogicalDataType",
    "OperationalDataBuilder",
    "OperationalDataModel",
    "OperationalDataSink",
    "OperationalRecord",
    "NullOperationalDataSink",
    "RelationshipDefinition",
    "build_operational_data_model",
]
