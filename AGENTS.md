# AGENTS.md

## Project

Green Direct Power Wind-PV-BESS batch simulation module.

The project is a technical simulation tool for green direct power projects.

## Current Scope

Implement V0.1 only:

- hourly energy balance;
- BESS SOC rolling calculation;
- batch scenario enumeration;
- policy compliance metrics;
- Excel/CSV export;
- basic Streamlit UI.

Do not implement economic evaluation in V0.1.

## Read First

Before editing code, read:

- PRD.md
- ALGORITHM_SPEC.md
- DATA_SCHEMA.md
- OUTPUT_SCHEMA.md
- TEST_CASES.md
- UI_SPEC.md
- ECONOMY_EXTENSION_SPEC.md

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

## Required Project Layout

```text
src/green_direct/
├─ io/
├─ models/
├─ core/
├─ batch/
├─ export/
├─ economy/
├─ ui/
└─ cli.py
tests/
config/
outputs/
```

## Critical Algorithm Rules

- BESS can only charge from surplus renewable generation.
- BESS cannot charge from grid.
- BESS cannot charge and discharge in the same hour.
- SOC must roll from one hour to the next.
- SOC must stay within soc_min and soc_max.
- BESS charge/discharge must respect power and energy limits.
- Keep dt as a parameter even if dt = 1 hour.
- Support both 8760 and 8784 rows.
- Do not mix economic evaluation into V0.1.
- Keep hourly detail outputs.

## Done Means

A task is done only when:

1. code runs;
2. tests pass;
3. no critical algorithm rule is violated;
4. outputs match OUTPUT_SCHEMA.md;
5. errors are user-friendly;
6. changed files are summarized.
