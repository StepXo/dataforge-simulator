"""Path resolution shared by public scenario entry points."""

from pathlib import Path


def resolve_scenario_path(argument: Path) -> Path:
    """Resolve an explicit file first, then the conventional scenario directory."""
    if argument.is_file():
        return argument
    candidate = Path("configs/scenarios") / f"{argument}.yaml"
    return candidate if candidate.is_file() else argument
