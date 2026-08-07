"""Event emitted after successful state validation."""

from dataforge.core.events.event import DomainEvent
from dataforge.engines.validation.models import ValidationContext


class StateValidationCompleted(DomainEvent):
    def __init__(self, validation: ValidationContext) -> None:
        super().__init__(
            event_type="StateValidationCompleted",
            payload={
                "tick_index": validation.tick_index,
                "current_time": validation.current_time.isoformat(),
                "checks_executed": validation.checks_executed,
                "collections_checked": validation.collections_checked,
                "valid": validation.valid,
            },
        )
