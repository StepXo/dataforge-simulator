"""Format-independent incremental operational output contracts."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

OperationalValue = str | int | float | Decimal | bool | date | datetime | None


@dataclass(frozen=True, slots=True)
class OperationalRecord:
    """Associate one logical row with its ODM dataset."""

    dataset: str
    values: Mapping[str, OperationalValue]


class OperationalDataSink(Protocol):
    """Consume operational records in lifecycle order."""

    def write_master(self, records: Iterable[OperationalRecord]) -> None: ...

    def write_tick(
        self, tick_index: int, records: Iterable[OperationalRecord]
    ) -> None: ...

    def write_final(self, records: Iterable[OperationalRecord]) -> None: ...

    def close(self) -> None: ...


class NullOperationalDataSink:
    """Accept and discard incremental output without retaining rows."""

    def write_master(self, records: Iterable[OperationalRecord]) -> None:
        self._discard(records)

    def write_tick(self, tick_index: int, records: Iterable[OperationalRecord]) -> None:
        del tick_index
        self._discard(records)

    def write_final(self, records: Iterable[OperationalRecord]) -> None:
        self._discard(records)

    def close(self) -> None:
        """Finish the no-op sink."""

    @staticmethod
    def _discard(records: Iterable[OperationalRecord]) -> None:
        for _ in records:
            pass
