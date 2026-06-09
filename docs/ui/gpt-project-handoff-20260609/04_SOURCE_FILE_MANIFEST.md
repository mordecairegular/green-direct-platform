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

Current implemented code baseline:

```text
c93d17a9f03dbafd113d90ab229680be296250cc
feat(ui): surface price-curve workflow and landed price metrics
```

GitHub remote:

```text
Not configured locally. `git remote -v` returns empty.
```

Do not invent a GitHub URL. After the user pushes the repo, use:

```text
https://github.com/<owner>/<repo>/tree/codex/UI
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
docs/ui/audit-20260606-product-design/screenshots/01-welcome.png
docs/ui/audit-20260606-product-design/screenshots/40-streamlit-02-simulation-guardrail.png
docs/ui/audit-20260606-product-design/screenshots/streamlit-20260609-landed-price-cards.png
docs/ui/audit-20260606-product-design/screenshots/23-recommendation-after-economy.png
docs/ui/audit-20260606-product-design/screenshots/streamlit-20260609-chart-overview-landed-cards.png
docs/ui/audit-20260606-product-design/screenshots/52-streamlit-20260608-chart-detail-selector.png
docs/ui/audit-20260606-product-design/screenshots/25-export-after-economy.png
```

If file upload limits are tight, prioritize:

```text
01-welcome.png
40-streamlit-02-simulation-guardrail.png
streamlit-20260609-landed-price-cards.png
streamlit-20260609-chart-overview-landed-cards.png
```

## Known Untracked Local Reference Folders

These are intentionally not part of the last code commit:

```text
docs/UI-suggest/20260609screenshot/
samples/示例-作废/
```

Treat them as optional local references only. Do not assume they are part of the canonical repo state unless the user explicitly uploads or commits them later.
