# Dispatch Core Status V0.2

This document records the actual current status of the dispatch core after the
first protective architecture updates. It is a status note, not a future design
specification.

## 1. Implemented Capabilities

- `DispatchStrategy` enum has been introduced.
- The currently supported strategy is:
  - `GRID_CONNECTED_RENEWABLE_FIRST_GREEDY`
- `run_single_scenario()` supports an optional `strategy` parameter.
- If no strategy is provided, the default remains
  `GRID_CONNECTED_RENEWABLE_FIRST_GREEDY`.
- `summary` records the selected `dispatch_strategy`.
- The `hourly_detail` DataFrame is now explicitly treated as the V0.1 physical
  implementation of `HourlyEnergyLedger`.
- `HOURLY_LEDGER_COLUMNS` is the explicit hourly ledger field list.
- `HOURLY_COLUMNS` remains as a backward-compatible alias of
  `HOURLY_LEDGER_COLUMNS`.
- A lightweight `InputDiagnostics` structure has been introduced for structured
  input and run diagnostics.
- `ScenarioResult` can now carry `diagnostics` while preserving the existing
  `warnings` list.
- Curve-cleaning warnings can be mirrored into structured diagnostics.

## 2. Not Implemented

The following capabilities are not implemented in the current dispatch core:

- Diesel generation.
- Off-grid dispatch.
- HOMER Combined Dispatch.
- Economic optimal dispatch.
- MILP optimization.
- Complex `ScenarioResult` metadata migration.
- A full input validation framework.
- UI-level diagnostics rendering.

## 3. Architecture Principles

- Technical simulation should first generate the hourly fact ledger:
  `hourly_detail`.
- Policy evaluation, economic evaluation, charts, reports, and exports should
  read from the hourly ledger and technical summary.
- Upper-layer modules should not recompute core dispatch, SOC, grid exchange,
  export, or curtailment logic.
- Economic ranking must not mutate or reverse-change technical dispatch results.
- Input diagnostics are an additive reporting layer. They must not silently
  tighten existing V0.1 validation rules or change calculation results.

## 4. Suggested Next Steps

- If development continues, prioritize input diagnostics or test hardening.
- Defer `ScenarioResult` metadata refactoring for now.
- Defer diesel generation and off-grid dispatch models for now.
