"""Physical consumers of DataForge analytical records."""

from dataforge.export.analytical.duckdb_sink import (
    DuckDBAnalyticalSink,
    DuckDBOperationalAnalyticsSink,
)

__all__ = ["DuckDBAnalyticalSink", "DuckDBOperationalAnalyticsSink"]
