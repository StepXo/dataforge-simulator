"""Minimal typed execution of supported business queries in DuckDB."""

import duckdb

from dataforge.analytics.business.queries import QUERIES, BusinessQuery
from dataforge.export.operational.sink import OperationalValue

type BusinessQueryRow = dict[str, OperationalValue]


def run_business_query(
    connection: duckdb.DuckDBPyConnection,
    query: BusinessQuery,
) -> tuple[BusinessQueryRow, ...]:
    """Execute one supported query and return simple name-to-value rows."""
    cursor = connection.execute(QUERIES[query])
    names = tuple(item[0] for item in cursor.description)
    return tuple(dict(zip(names, row, strict=True)) for row in cursor.fetchall())


__all__ = ["BusinessQueryRow", "run_business_query"]
