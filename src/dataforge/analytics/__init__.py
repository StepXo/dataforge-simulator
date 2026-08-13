"""Public analytical model contracts."""

from dataforge.analytics.builder import AnalyticalDataBuilder
from dataforge.analytics.model import (
    AnalyticalColumnDefinition,
    AnalyticalDatasetDefinition,
    AnalyticalDatasetKind,
    AnalyticalModel,
    AnalyticalRecord,
    AnalyticalRelationshipDefinition,
)
from dataforge.analytics.schema import build_analytical_model

__all__ = [
    "AnalyticalColumnDefinition",
    "AnalyticalDataBuilder",
    "AnalyticalDatasetDefinition",
    "AnalyticalDatasetKind",
    "AnalyticalModel",
    "AnalyticalRecord",
    "AnalyticalRelationshipDefinition",
    "build_analytical_model",
]
