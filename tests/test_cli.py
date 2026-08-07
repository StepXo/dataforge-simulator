"""Tests for the local developer CLI."""

import subprocess
from pathlib import Path
from unittest.mock import call, patch

import pytest
from typer.testing import CliRunner

from dataforge.cli.app import app, find_project_root, run_process

runner = CliRunner()


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command_name in (
        "setup",
        "run",
        "test",
        "lint",
        "format",
        "typecheck",
        "check",
        "dev",
    ):
        assert command_name in result.output


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            ["run"],
            [
                "uvicorn",
                "dataforge.api.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--reload",
            ],
        ),
        (
            ["run", "--host", "0.0.0.0", "--port", "8080", "--no-reload"],
            [
                "uvicorn",
                "dataforge.api.app:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8080",
            ],
        ),
    ],
)
def test_run_builds_server_command(arguments: list[str], expected: list[str]) -> None:
    with patch("dataforge.cli.app.run_process", return_value=0) as process:
        result = runner.invoke(app, arguments)

    assert result.exit_code == 0
    process.assert_called_once_with(expected)


def test_run_rejects_invalid_port() -> None:
    with patch("dataforge.cli.app.run_process") as process:
        result = runner.invoke(app, ["run", "--port", "0"])

    assert result.exit_code != 0
    process.assert_not_called()


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["test"], ["pytest"]),
        (
            ["test", "--", "tests/api/test_health.py"],
            ["pytest", "tests/api/test_health.py"],
        ),
        (["test", "--", "-k", "preview", "-x"], ["pytest", "-k", "preview", "-x"]),
    ],
)
def test_test_forwards_arguments(arguments: list[str], expected: list[str]) -> None:
    with patch("dataforge.cli.app.run_process", return_value=0) as process:
        result = runner.invoke(app, arguments)

    assert result.exit_code == 0
    process.assert_called_once_with(expected)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["lint"], ["ruff", "check", "."]),
        (["lint", "--fix"], ["ruff", "check", ".", "--fix"]),
        (["format"], ["ruff", "format", "--check", "."]),
        (["format", "--write"], ["ruff", "format", "."]),
        (["typecheck"], ["mypy", "src"]),
        (["setup"], ["uv", "sync", "--dev"]),
    ],
)
def test_quality_and_setup_commands(arguments: list[str], expected: list[str]) -> None:
    with patch("dataforge.cli.app.run_process", return_value=0) as process:
        result = runner.invoke(app, arguments)

    assert result.exit_code == 0
    process.assert_called_once_with(expected)


def test_check_runs_stages_in_order() -> None:
    with patch("dataforge.cli.app.run_process", return_value=0) as process:
        result = runner.invoke(app, ["check"])

    assert result.exit_code == 0
    assert process.call_args_list == [
        call(["ruff", "format", "--check", "."]),
        call(["ruff", "check", "."]),
        call(["mypy", "src"]),
        call(["pytest"]),
    ]


def test_check_stops_at_first_failure_and_propagates_exit_code() -> None:
    with patch("dataforge.cli.app.run_process", side_effect=[0, 9]) as process:
        result = runner.invoke(app, ["check"])

    assert result.exit_code == 9
    assert process.call_args_list == [
        call(["ruff", "format", "--check", "."]),
        call(["ruff", "check", "."]),
    ]


@pytest.mark.parametrize(
    ("arguments", "expected_calls"),
    [
        (
            ["dev"],
            [
                call(
                    [
                        "uvicorn",
                        "dataforge.api.app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                        "--reload",
                    ]
                )
            ],
        ),
        (
            ["dev", "--test", "--no-reload"],
            [
                call(["pytest"]),
                call(
                    [
                        "uvicorn",
                        "dataforge.api.app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                    ]
                ),
            ],
        ),
        (
            ["dev", "--check", "--port", "8080"],
            [
                call(["ruff", "format", "--check", "."]),
                call(["ruff", "check", "."]),
                call(["mypy", "src"]),
                call(["pytest"]),
                call(
                    [
                        "uvicorn",
                        "dataforge.api.app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8080",
                        "--reload",
                    ]
                ),
            ],
        ),
    ],
)
def test_dev_workflows(arguments: list[str], expected_calls: list[call]) -> None:
    with patch("dataforge.cli.app.run_process", return_value=0) as process:
        result = runner.invoke(app, arguments)

    assert result.exit_code == 0
    assert process.call_args_list == expected_calls


@pytest.mark.parametrize("validation_option", ["--test", "--check"])
def test_dev_does_not_start_server_after_failure(validation_option: str) -> None:
    with patch("dataforge.cli.app.run_process", return_value=7) as process:
        result = runner.invoke(app, ["dev", validation_option])

    assert result.exit_code == 7
    process.assert_called_once()
    assert process.call_args.args[0][0] != "uvicorn"


def test_dev_rejects_test_and_check_together() -> None:
    with patch("dataforge.cli.app.run_process") as process:
        result = runner.invoke(app, ["dev", "--test", "--check"])

    assert result.exit_code != 0
    process.assert_not_called()


def test_command_failure_exit_code_is_propagated() -> None:
    with patch("dataforge.cli.app.run_process", return_value=23):
        result = runner.invoke(app, ["lint"])

    assert result.exit_code == 23


def test_process_runs_from_root_when_called_in_subdirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    nested = root / "tests" / "unit"
    nested.mkdir(parents=True)
    (root / "pyproject.toml").touch()
    monkeypatch.chdir(nested)
    completed = subprocess.CompletedProcess(["pytest"], returncode=0)

    with (
        patch("dataforge.cli.app.shutil.which", return_value="pytest"),
        patch("dataforge.cli.app.subprocess.run", return_value=completed) as process,
    ):
        assert run_process(["pytest"]) == 0

    assert find_project_root() == root
    process.assert_called_once_with(["pytest"], cwd=root, check=False)


def test_process_reports_missing_executable() -> None:
    with patch("dataforge.cli.app.shutil.which", return_value=None):
        assert run_process(["missing-tool"]) == 127


def test_process_reports_missing_project_root(tmp_path: Path) -> None:
    with patch("dataforge.cli.app.Path.cwd", return_value=tmp_path):
        assert run_process(["pytest"]) == 2


def test_process_handles_keyboard_interrupt() -> None:
    with (
        patch("dataforge.cli.app.shutil.which", return_value="uvicorn"),
        patch("dataforge.cli.app.subprocess.run", side_effect=KeyboardInterrupt),
    ):
        assert run_process(["uvicorn"]) == 130
