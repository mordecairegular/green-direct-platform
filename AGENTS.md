# AGENTS.md

## Project

Green Direct Power and Microgrid Planning Platform.

This repository started as a V0.1 Wind-PV-BESS batch technical simulation module. The current product direction has been reframed: the software should evolve into a planning and recommendation platform for green direct power / microgrid projects.

The old V0.1 technical simulator remains a valuable baseline. Do not discard it. Future work should build on it while introducing clearer project context, energy ledger, scenario recommendation, lightweight economics, and diesel/off-grid extension capability.

## Current Product Direction

The user does not want to see a raw table of every enumerated scenario as the primary output. Enumeration is an internal search method.

The target workflow is:

```text
project inputs
-> input diagnostics
-> candidate scenario generation
-> hourly technical simulation
-> policy feasibility filtering
-> lightweight economic ranking
-> representative scenario recommendation
-> charts / reports / exports around selected representative scenarios
```

Representative scenarios may include:

- recommended balanced scenario;
- policy-compliant lowest-cost scenario;
- high green-load-rate scenario;
- high self-use / low-export scenario;
- low-curtailment scenario;
- low-capacity or low-storage scenario;
- off-grid reliability scenario when diesel/off-grid logic exists;
- user-pinned scenario.

## V0.1 Baseline Status

The existing V0.1 Wind-PV-BESS logic is a baseline for regression and review, not the final product boundary.

Baseline documents:

- `PRD.md`
- `ALGORITHM_SPEC.md`
- `DATA_SCHEMA.md`
- `OUTPUT_SCHEMA.md`
- `TEST_CASES.md`
- `UI_SPEC.md`
- `ECONOMY_EXTENSION_SPEC.md`
- `docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`
- `notes/PRODUCT_POLISH_LOG.md`

When modifying current Wind-PV-BESS technical logic, preserve the baseline rules unless the user explicitly asks to change the calculation口径 and the related tests and documents are updated.

## Read First

Before architecture or feature work, read:

- `AGENTS.md`
- `CLAUDE.md`
- `notes/HANDOFF_FOR_NEW_MACHINE.md`
- `notes/architecture_reframe_20260519/01_EXPERT_REVIEW_BRIEF.md`
- `notes/architecture_reframe_20260519/02_TARGET_ARCHITECTURE_AND_CALCULATION_LOGIC.md`
- `notes/architecture_reframe_20260519/03_MIGRATION_AND_POLISH_PLAN.md`
- `notes/architecture_reframe_20260519/04_HOURLY_DISPATCH_LOGIC_WITH_DIESEL.md`
- `docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`
- `notes/PRODUCT_POLISH_LOG.md`

Before changing existing V0.1 core simulation behavior, also read:

- `ALGORITHM_SPEC.md`
- `TEST_CASES.md`
- `OUTPUT_SCHEMA.md`

## Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run tests:

```bash
pytest
```

Run Streamlit app:

```bash
streamlit run src/green_direct/ui/app.py
```

## Architecture Direction

Prefer evolving toward these concepts:

```text
ProjectStudy
InputDiagnostics
ScenarioPool
CandidateScenario
HourlyEnergyLedger
DispatchStrategy
PolicyEvaluation
EconomicEvaluation
ScenarioRecommendation
RecommendationPortfolio
StudyResult
ResultStore
```

Recommended future package areas:

```text
src/green_direct/
├─ domain/          # project, assets, scenario, ledger, diagnostics models
├─ engine/          # dispatch strategies, simulation, metrics, policy
├─ services/        # study runner, result store, orchestration
├─ recommendation/  # filtering, ranking, representative scenario selection
├─ economy/         # lightweight ranking first, full finance later
├─ io/
├─ models/
├─ core/
├─ batch/
├─ export/
├─ visualization/
├─ ui/
└─ cli.py
```

Do not rush a full folder migration. Introduce these layers incrementally and keep old tests passing.

## Core Modeling Principles

- Treat hourly detail as the source of truth. Future modules should read a unified energy ledger rather than recomputing hidden口径.
- Policy evaluation, economy, charts, reports, and AI-style explanation must read technical simulation results; they must not silently mutate dispatch results.
- If a future economic optimization or alternative dispatch policy is introduced, implement it as an explicit named `DispatchStrategy` or optimization engine, not as an invisible change to the baseline greedy dispatch.
- Keep `scenario_id` as the cross-module key.
- Keep units explicit. Current power unit is 万千瓦, energy unit is 万千瓦时, and ratios are internal decimals.
- Prefer structured diagnostics over plain error strings: severity, source, code, message, location, suggestion.
- Do not force every uncertain data preparation or parameter derivation into the web UI. If a data transformation is easier, clearer, or more auditable in CSV/Excel templates, prefer a spreadsheet input path or discuss the boundary before adding more UI controls.

## Baseline Wind-PV-BESS Rules

For the current baseline renewable-charged BESS strategy:

- BESS can only charge from surplus renewable generation.
- BESS cannot charge from grid.
- BESS cannot charge and discharge in the same hour.
- BESS cannot discharge to grid.
- SOC must roll from one hour to the next.
- SOC must stay within `soc_min` and `soc_max`.
- BESS charge/discharge must respect power and energy limits.
- Keep `dt_hours` as a parameter even if `dt_hours = 1`.
- Support both 8760 and 8784 rows.
- Keep hourly detail outputs for any scenario that is selected for review, charts, reports, or audit.

If diesel generator or grid-charging behavior is later introduced, source tagging must be explicit. Do not let diesel/grid energy be counted as renewable self-use.

## Diesel Extension Principles

Diesel generation is allowed in future work and should be modeled as a dispatchable asset, not as a special case hidden inside grid import.

Future diesel logic should define:

- installed diesel capacity;
- minimum and maximum output;
- optional minimum stable load;
- fuel consumption model;
- variable O&M and fuel cost;
- emission factor;
- dispatch order in each project mode;
- whether diesel may charge BESS;
- reliability and unserved-load treatment in off-grid mode.

Grid-connected projects may include diesel, although it is less common. Off-grid and hybrid backup modes should be first-class modes rather than hacks around `allow_export`.

## Economy Principles

Lightweight economic ranking is now in scope as a scenario selection layer. Full financial evaluation can still be phased.

Start with ranking-oriented outputs such as:

- capex estimate;
- fixed and variable O&M;
- grid purchase cost;
- diesel fuel cost;
- export revenue;
- annual net cost;
- LCOE-like screening metric;
- simple payback if inputs are sufficient.

Later full finance may include:

- NPV;
- IRR;
- project cash flow;
- tax;
- depreciation;
- financing;
- residual value.

Economy modules must be linked to technical results through `scenario_id`.

## Recommendation Principles

Do not expose raw enumeration as the primary user experience.

The main result should be a small, explainable `RecommendationPortfolio`, with each selected scenario carrying:

- label;
- scenario_id;
- capacity configuration;
- key technical metrics;
- key economic metrics if available;
- feasibility status;
- recommendation reason;
- trade-off notes;
- links to hourly ledger / charts / export files.

## Chart Module Priority

The current chart module is an early prototype and is not a protected architecture anchor. It may be replaced or discarded if it blocks clearer product development.

Near-term priority is:

1. hourly simulation and energy ledger correctness;
2. Wind-PV-BESS sizing and candidate scenario logic;
3. lightweight economic ranking;
4. policy filtering and representative scenario recommendation;
5. then redesigned charts and reports around selected scenarios.

Do not spend major effort polishing the existing chart module before the calculation, sizing, economy, and recommendation logic are stable.

## Done Means

A task is done only when:

1. code or documentation matches the current product direction;
2. existing baseline tests are not broken, unless the task is documentation-only;
3. critical algorithm rules are not violated silently;
4. output schemas or new schemas are documented when changed;
5. errors and diagnostics are user-friendly;
6. changed files are summarized.

For documentation-only tasks, run tests only if code behavior or executable examples changed.

## Persistent Memory Rules

Do not rely on chat history as the only memory. Important decisions must be written into project documents.

Update `notes/PRODUCT_POLISH_LOG.md` when product direction, calculation口径, UX workflow, diesel logic, economy logic, recommendation logic, or expert feedback changes.

Update `notes/HANDOFF_FOR_NEW_MACHINE.md` when the next-session startup prompt, required reading list, project positioning, development order, or cross-machine continuation instructions change.
