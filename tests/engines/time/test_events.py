"""Tests for events emitted by the time engine."""

import json
from datetime import datetime, timedelta, timezone

from dataforge.core.tick import TickUnit
from dataforge.engines.time.events import TimeContextGenerated
from dataforge.engines.time.models import TemporalContext


def test_time_context_generated_has_exact_serializable_payload() -> None:
    offset = timezone(timedelta(hours=-5))
    temporal = TemporalContext(
        tick_index=0,
        current_time=datetime(2026, 8, 15, 12, tzinfo=offset),
        tick_unit=TickUnit.HOUR,
    )

    event = TimeContextGenerated(temporal)

    assert event.event_type == "TimeContextGenerated"
    assert event.payload == {
        "tick_index": 0,
        "current_time": "2026-08-15T12:00:00-05:00",
        "tick_unit": "hour",
        "year": 2026,
        "quarter": 3,
        "month": 8,
        "day": 15,
        "hour": 12,
        "day_of_week": 5,
        "day_name": "Saturday",
        "time_of_day": "lunch",
        "is_weekend": True,
        "is_month_start": False,
        "is_month_end": False,
        "is_mid_month": True,
    }
    assert json.loads(json.dumps(event.payload)) == event.payload
