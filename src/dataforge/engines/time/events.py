"""Events published by the time engine."""

from dataforge.engines.time.models import TemporalContext
from dataforge.events.event import DomainEvent


class TimeContextGenerated(DomainEvent):
    """Record generation of temporal context for one simulated tick."""

    def __init__(self, temporal_context: TemporalContext) -> None:
        super().__init__(
            event_type="TimeContextGenerated",
            payload={
                "tick_index": temporal_context.tick_index,
                "current_time": temporal_context.current_time.isoformat(),
                "tick_unit": temporal_context.tick_unit.value,
                "year": temporal_context.year,
                "quarter": temporal_context.quarter,
                "month": temporal_context.month,
                "day": temporal_context.day,
                "hour": temporal_context.hour,
                "day_of_week": temporal_context.day_of_week,
                "day_name": temporal_context.day_name,
                "time_of_day": temporal_context.time_of_day.value,
                "is_weekend": temporal_context.is_weekend,
                "is_month_start": temporal_context.is_month_start,
                "is_month_end": temporal_context.is_month_end,
                "is_mid_month": temporal_context.is_mid_month,
            },
        )
