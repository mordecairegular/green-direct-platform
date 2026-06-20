# PROJECT_STRUCTURE.md：推荐项目结构

```text
green-direct-calculator/
├─ README.md
├─ PRD.md
├─ ALGORITHM_SPEC.md
├─ DATA_SCHEMA.md
├─ OUTPUT_SCHEMA.md
├─ TEST_CASES.md
├─ UI_SPEC.md
├─ ECONOMY_EXTENSION_SPEC.md
├─ ROADMAP.md
├─ CLAUDE.md
├─ AGENTS.md
├─ requirements.txt
├─ pyproject.toml
├─ config/
│  ├─ default_params.yaml
│  └─ scenario_grid.example.yaml
├─ data/
│  └─ examples/
├─ outputs/
├─ src/
│  └─ green_direct/
│     ├─ __init__.py
│     ├─ cli.py
│     ├─ io/
│     │  ├─ __init__.py
│     │  ├─ read_curves.py
│     │  └─ validators.py
│     ├─ models/
│     │  ├─ __init__.py
│     │  ├─ params.py
│     │  ├─ scenario.py
│     │  └─ results.py
│     ├─ core/
│     │  ├─ __init__.py
│     │  ├─ bess_dispatch.py
│     │  ├─ single_scenario_simulator.py
│     │  └─ metrics.py
│     ├─ batch/
│     │  ├─ __init__.py
│     │  ├─ scenario_generator.py
│     │  └─ batch_runner.py
│     ├─ export/
│     │  ├─ __init__.py
│     │  ├─ excel_exporter.py
│     │  └─ csv_exporter.py
│     ├─ economy/
│     │  ├─ __init__.py
│     │  ├─ economic_inputs.py
│     │  └─ economic_evaluator.py
│     └─ ui/
│        ├─ __init__.py
│        └─ app.py
└─ tests/
   ├─ test_data_validation.py
   ├─ test_single_scenario.py
   ├─ test_bess_dispatch.py
   ├─ test_batch_runner.py
   ├─ test_metrics.py
   └─ test_export.py
```
