# Agent guidelines

## Quality and scope

- Run the validations required by the task before reporting completion; never claim a check passed unless it was actually executed successfully.
- Preserve public CLI, API, scenario, and data contracts unless the current requirement explicitly changes them, and update tests and documentation when behavior changes.
- Do not add dependencies, abstractions, infrastructure, or patterns unless the current requirement justifies them.
- Prefer explicit composition and small contracts over registries, factories, managers, service locators, or hidden framework behavior.

## Architecture

- Keep package boundaries clear: Core must not depend on engines, API, CLI, or physical exporters, and domain components must not access external surfaces directly.
- `SimulationRunner` is the explicit composition root; `SimulationOrchestrator` exclusively owns the tick loop and clock advancement.
- Engines operate through `SimulationContext` and `SimulationState`, stay within their domain responsibility, and never execute other engines or duplicate their business logic.
- Bootstrap generators create initial and master state; engines evolve runtime state, and shared state must not use globals or singletons.
- `StateValidationEngine` remains the final engine of every tick; invalid state must fail instead of being repaired silently.
- Scenario paths and filenames carry no business semantics; validated configuration content is the source of truth.

## Determinism and temporal semantics

- All simulation randomness must use `RandomEngine`; the same scenario and seed must remain reproducible.
- Extending `end_datetime` must not rewrite bootstrap state or previously simulated ticks.
- Demand ranges are hourly baselines and must scale with tick duration, including the intraday profile for daily ticks.
- Replenishment lead times are expressed in days and must retain their business meaning across tick resolutions.

## Domain invariants

- Never use `float` for money; monetary values and serialization must preserve `Decimal` exactly.
- `InventoryItem` defines the Location × Product assortment: missing means not offered, while zero stock means offered but unavailable; stock must never become negative.
- `Transaction` represents one basket or checkout, while `TransactionLine` represents a product-level outcome.
- Engines must preserve commercial conservation invariants and must not allow activity before a Location opens.

## Streaming and export

- Historical tick state may be released only after validation and successful sink consumption; a failed write must prevent eviction and clock advancement.
- Streaming and full-history modes must produce equivalent business results, while streaming must not retain complete tick history unnecessarily.
- The Operational Data Model remains independent of CSV, Parquet, SQL, and analytics schemas; physical exporters consume operational records incrementally.
- CSV and Parquet must expose identical logical datasets, and Arrow schemas must be derived from the Operational Data Model.
