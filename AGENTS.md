# Agent guidelines

- Preserve the current FastAPI service and backward compatibility of existing endpoints.
- Run `uv sync --dev`, Ruff format and lint checks, `mypy src`, Pytest, and the Docker build before completing a feature.
- Use `uv run dataforge check` as a convenient local validation, while preserving and respecting CI's explicit independent commands.
- Do not add dependencies or abstractions unless the current feature requires them.
- Update tests and `README.md` whenever behavior changes.
- Never report a validation as passing unless it was actually executed successfully.
