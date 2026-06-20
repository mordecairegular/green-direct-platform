# Source File Manifest For ChatGPT Project

Use this file to decide what to upload or what to ask the GitHub connector to read.

## Repository Status

Local repository path:

```text
Z:\Projects\20260515_8760
```

Current branch:

```text
codex/UI
```

GitHub repository:

```text
https://github.com/mordecairegular/green-direct-platform
```

Branch URL:

```text
https://github.com/mordecairegular/green-direct-platform/tree/codex/UI
```

Last committed local HEAD before this handoff refresh:

```text
6432f15e6738397db1a5784e66ad21a6da399146
docs(ui): add ChatGPT Project handoff package
```

This folder has local working-copy updates for the 2026-06-09 GPT Project handoff. If those updates are not pushed to GitHub, upload this folder's Markdown files manually to ChatGPT Project.

Current implemented UI/economy baseline before the docs-only handoff commit:

```text
c93d17a9f03dbafd113d90ab229680be296250cc
feat(ui): surface price-curve workflow and landed price metrics
```

GitHub remote:

```text
origin https://github.com/mordecairegular/green-direct-platform.git
```

## Most Important Files For UI Review

Project instructions and product context:

```text
AGENTS.md
notes/HANDOFF_FOR_NEW_MACHINE.md
notes/PRODUCT_POLISH_LOG.md
docs/WEB_APP_WORKFLOW_AND_UI_RESTRUCTURE.md
docs/ui/UI_IMPLEMENTATION_MAPPING_20260606.md
docs/ui/UI_MAPPING_SELF_AUDIT_20260608.md
```

Current Streamlit UI:

```text
src/green_direct/ui/app.py
src/green_direct/visualization/chart_ui.py
```

Economy / price curve display data paths:

```text
src/green_direct/economy/price_curves.py
src/green_direct/services/study_runner.py
src/green_direct/recommendation/recommendation_engine.py
src/green_direct/economy/economic_evaluator.py
src/green_direct/economy/single_entity_evaluator.py
```

Tests that explain expected behavior:

```text
tests/test_ui_import.py
tests/test_visualization_smoke.py
tests/test_chart_data.py
tests/test_price_curves.py
tests/test_study_runner.py
```

Price curve docs/templates:

```text
docs/PRICE_CURVE_ECONOMY_CALCULATION_METHOD.md
docs/templates/price_curves/README.md
docs/templates/price_curves/price_curve_template_down_grid.csv
samples/price_curve_template_down_grid.csv
```

Audit and prototype:

```text
docs/ui/audit-20260606-product-design/UI_AUDIT_REPORT.md
docs/ui/audit-20260606-product-design/UI_REDESIGN_ROADMAP.md
docs/ui/audit-20260606-product-design/FLOW_CAPTURE_NOTES.md
docs/ui/prototype-dashboard.html
```

## Screenshots To Upload If Visual Review Is Needed

Recommended minimal screenshot batch:

```text
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/01-main-long-project-launch.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/02-main-long-simulation-before-demo.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/03-main-long-simulation-after-demo.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/05-main-long-economy-after-run.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/06-main-long-recommendation.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/07-main-long-chart-overview-and-detail.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/08-main-long-export-center.png
```

If file upload limits are tight, prioritize:

```text
01-main-long-project-launch.png
03-main-long-simulation-after-demo.png
05-main-long-economy-after-run.png
07-main-long-chart-overview-and-detail.png
08-main-long-export-center.png
```

For screenshot purpose and upload order, see:

```text
docs/ui/gpt-project-handoff-20260609/05_SCREENSHOT_AND_RECORDING_CHECKLIST.md
```

## Known Untracked Local Reference Folders

These are intentionally not part of the last code commit:

```text
docs/UI-suggest/20260609screenshot/
samples/示例-作废/
```

Treat them as optional local references only. Do not assume they are part of the canonical repo state unless the user explicitly uploads or commits them later.
