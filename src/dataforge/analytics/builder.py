"""Incremental transformation from operational to analytical records."""

from collections.abc import Iterable, Iterator, Mapping
from datetime import date, datetime
from decimal import Decimal

from dataforge.analytics.model import AnalyticalRecord
from dataforge.export.operational.sink import OperationalRecord, OperationalValue

ZERO_MONEY = Decimal("0.00")


class AnalyticalDataBuilder:
    """Transform lifecycle-ordered ODM records without retaining tick history."""

    def __init__(self) -> None:
        self._countries: dict[str, Mapping[str, OperationalValue]] = {}
        self._regions: dict[str, Mapping[str, OperationalValue]] = {}
        self._areas: dict[str, Mapping[str, OperationalValue]] = {}
        self._cities: dict[str, Mapping[str, OperationalValue]] = {}
        self._categories: dict[str, str] = {}
        self._current_transaction: Mapping[str, OperationalValue] | None = None
        self._dates: set[date] = set()

    def transform(
        self, records: Iterable[OperationalRecord]
    ) -> Iterator[AnalyticalRecord]:
        """Yield analytical rows while consuming ordered operational rows once."""
        for record in records:
            yield from self._transform_record(record)

    def _transform_record(
        self, record: OperationalRecord
    ) -> Iterator[AnalyticalRecord]:
        values = record.values
        match record.dataset:
            case "countries":
                self._countries[_string(values, "country_id")] = values
            case "regions":
                self._regions[_string(values, "region_id")] = values
            case "administrative_areas":
                self._areas[_string(values, "administrative_area_id")] = values
            case "cities":
                self._cities[_string(values, "city_id")] = values
            case "categories":
                self._categories[_string(values, "category_id")] = _string(
                    values, "name"
                )
            case "locations":
                yield self._location(values)
            case "products":
                yield self._product(values)
            case "customers":
                yield AnalyticalRecord("dim_customer", dict(values))
            case "promotions":
                yield AnalyticalRecord("dim_promotion", dict(values))
            case "transactions":
                self._current_transaction = values
            case "transaction_lines":
                yield from self._sales(values)
            case "transaction_line_promotions":
                yield AnalyticalRecord("bridge_sales_promotion", dict(values))
            case "inventory_movements":
                occurred_at = _datetime(values, "occurred_at")
                yield from self._date_record(occurred_at.date())
                yield AnalyticalRecord(
                    "fact_inventory_movement",
                    {**values, "date": occurred_at.date()},
                )
            case "replenishments":
                created_at = _datetime(values, "created_at")
                yield from self._date_record(created_at.date())
                completed_at = values.get("completed_at")
                if isinstance(completed_at, datetime):
                    yield from self._date_record(completed_at.date())
                yield AnalyticalRecord(
                    "fact_replenishment",
                    {
                        "replenishment_id": values["replenishment_id"],
                        "inventory_id": values["inventory_id"],
                        "location_id": values["location_id"],
                        "product_id": values["product_id"],
                        "created_date": created_at.date(),
                        "completed_date": (
                            completed_at.date()
                            if isinstance(completed_at, datetime)
                            else None
                        ),
                        "requested_quantity": values["requested_quantity"],
                        "received_quantity": values.get("received_quantity"),
                        "requested_tick_index": values["requested_tick_index"],
                        "due_tick_index": values["due_tick_index"],
                        "completed_tick_index": values.get("completed_tick_index"),
                        "created_at": created_at,
                        "completed_at": completed_at,
                        "status": values["status"],
                    },
                )
            case "metrics":
                yield from self._date_record(_datetime(values, "current_time").date())

    def _location(self, values: Mapping[str, OperationalValue]) -> AnalyticalRecord:
        city = self._cities[_string(values, "city_id")]
        area = self._areas[_string(values, "administrative_area_id")]
        region = self._regions[_string(values, "region_id")]
        country = self._countries[_string(values, "country_id")]
        return AnalyticalRecord(
            "dim_location",
            {
                "location_id": values["location_id"],
                "location_name": values["name"],
                "city_id": city["city_id"],
                "city_name": city["name"],
                "administrative_area_id": area["administrative_area_id"],
                "administrative_area_name": area["name"],
                "administrative_area_type": area["area_type"],
                "region_id": region["region_id"],
                "region_name": region["name"],
                "country_id": country["country_id"],
                "country_code": country["code"],
                "country_name": country["name"],
                "capacity": values["capacity"],
                "activity_factor": values["activity_factor"],
                "opened_at": values["opened_at"],
            },
        )

    def _product(self, values: Mapping[str, OperationalValue]) -> AnalyticalRecord:
        category_id = _string(values, "category_id")
        return AnalyticalRecord(
            "dim_product",
            {
                "product_id": values["product_id"],
                "product_name": values["name"],
                "category_id": category_id,
                "category_name": self._categories[category_id],
                "currency": values["currency"],
                "base_price": values["base_price"],
                "base_cost": values["base_cost"],
                "base_margin": values["base_margin"],
                "activity_factor": values["activity_factor"],
                "active": values["active"],
            },
        )

    def _sales(
        self, line: Mapping[str, OperationalValue]
    ) -> Iterator[AnalyticalRecord]:
        transaction = self._current_transaction
        if (
            transaction is None
            or line["transaction_id"] != transaction["transaction_id"]
        ):
            raise ValueError("Transaction line must follow its operational transaction")
        occurred_at = _datetime(transaction, "occurred_at")
        yield from self._date_record(occurred_at.date())
        completed = line["status"] == "completed"
        quantity = _integer(line, "quantity")
        yield AnalyticalRecord(
            "fact_sales",
            {
                "transaction_line_id": line["transaction_line_id"],
                "transaction_id": transaction["transaction_id"],
                "basket_id": transaction["basket_id"],
                "customer_id": transaction["customer_id"],
                "product_id": line["product_id"],
                "location_id": transaction["location_id"],
                "date": occurred_at.date(),
                "occurred_at": occurred_at,
                "tick_index": transaction["tick_index"],
                "channel": transaction["channel"],
                "currency": transaction["currency"],
                "transaction_status": transaction["status"],
                "line_status": line["status"],
                "rejection_reason": line.get("rejection_reason"),
                "quantity": quantity,
                "unit_price": line["unit_price"],
                "completed_quantity": quantity if completed else 0,
                "rejected_quantity": 0 if completed else quantity,
                "gross_sales_amount": line["gross_amount"] if completed else ZERO_MONEY,
                "discount_amount": line["discount_amount"] if completed else ZERO_MONEY,
                "net_sales_amount": line["net_amount"] if completed else ZERO_MONEY,
                "lost_sales_amount": ZERO_MONEY if completed else line["net_amount"],
            },
        )

    def _date_record(self, value: date) -> Iterator[AnalyticalRecord]:
        if value in self._dates:
            return
        self._dates.add(value)
        iso = value.isocalendar()
        yield AnalyticalRecord(
            "dim_date",
            {
                "date": value,
                "year": value.year,
                "quarter": (value.month - 1) // 3 + 1,
                "month_number": value.month,
                "month_name": value.strftime("%B"),
                "iso_week": iso.week,
                "iso_week_year": iso.year,
                "iso_weekday": iso.weekday,
                "weekday_name": value.strftime("%A"),
                "weekend": iso.weekday >= 6,
            },
        )


def _string(values: Mapping[str, OperationalValue], name: str) -> str:
    value = values[name]
    if not isinstance(value, str):
        raise ValueError(f"Operational value must be a string: {name}")
    return value


def _integer(values: Mapping[str, OperationalValue], name: str) -> int:
    value = values[name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Operational value must be an integer: {name}")
    return value


def _datetime(values: Mapping[str, OperationalValue], name: str) -> datetime:
    value = values[name]
    if not isinstance(value, datetime):
        raise ValueError(f"Operational value must be a datetime: {name}")
    return value
