# Project Context For ChatGPT Project

GitHub repository:

```text
https://github.com/mordecairegular/green-direct-platform
```

Current local working branch for this UI review package:

```text
codex/UI
```

## Product

Green Direct Power and Microgrid Planning Platform.

The product started as a V0.1 Wind-PV-BESS batch technical simulation module. It is evolving into a planning and recommendation platform for green direct power / microgrid projects.

The target user does not want a raw table of all enumerated scenarios as the primary output. Enumeration is an internal search method. The user wants a clear workflow that helps compare feasible, representative, and economically meaningful scenarios.

## Target Workflow

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

Current UI pages:

```text
01 项目启动台 / 欢迎页
02 方案仿真
03 经济测算
04 方案推荐
05 图表概览
06 图表下载和报告生成
```

## Hard Constraints

- Do not change core technical dispatch or scenario calculation rules unless explicitly requested.
- Keep existing Wind-PV-BESS baseline logic stable:
  - BESS only charges from surplus renewable generation.
  - BESS cannot charge from grid.
  - BESS cannot discharge to grid.
  - BESS cannot charge and discharge in the same hour.
  - SOC rolls hour to hour and stays within bounds.
  - Technical simulation remains the source of truth for economy, recommendation, charts, and export.
- UI recommendations may change information architecture, page grouping, components, copy, state flow, chart choices, and export workflow.
- Avoid decorative "make it modern" advice. This is a professional engineering planning tool; clarity, auditability, and decision quality matter more than visual flourish.

## Latest Implemented UI Baseline

As of 2026-06-09, recent Streamlit work has already implemented several ideas that may still need review:

- six-step workbench navigation;
- project launch/status page;
- scenario simulation page with both capacity-range enumeration and specified single-scenario input;
- project-level down-grid electricity price curve upload on the scenario simulation page;
- economy page that automatically reuses the project-level price curve;
- landed load price before/after green power display;
- recommendation cards with technical/economic metrics and merged labels;
- chart overview with policy bottom-margin matrix, curtailment rate as a low-priority operational indicator, capacity configuration structure matrix, and scenario quick buttons;
- centralized export/report page.

The UI review should evaluate whether these implementations are clear and decision-useful, not assume they are still only ideas.

## Important Recent Decisions

### Electricity price curve workflow

The down-grid electricity price curve is a project-level input. It is uploaded on the scenario simulation/input page and reused by later economy and recommendation calculations. The economy page should not ask the user to upload the same price curve again.

If the user provides an hourly down-grid price curve, later calculations should use the curve. If no hourly curve is provided, fixed user-entered landed prices are used.

### Confirmed landed load price口径

Before green power:

```text
With hourly down-grid price:
sum(hourly load energy * hourly down-grid landed price with VAT) / total load energy

Without hourly down-grid price:
fixed down-grid landed price with VAT supplied by the user
```

After green power:

```text
With hourly down-grid price:
(sum(hourly down-grid energy * hourly down-grid landed price with VAT)
 + green self-use energy * (green power settlement price with VAT
   + transmission & distribution tariff
   + government fund and surcharge))
/ total load energy

Without hourly down-grid price:
(down-grid energy * fixed down-grid landed price with VAT
 + green self-use energy * (green power settlement price with VAT
   + transmission & distribution tariff
   + government fund and surcharge))
/ total load energy
```

The UI should make the difference before/after green power easy to understand. Key fields may include:

- load landed price before green power;
- load landed price after green power;
- price delta;
- green load rate;
- green settlement price;
- weighted down-grid landed price;
- down-grid ratio;
- self-use energy / down-grid energy where helpful.

## Current UI Pain Points To Review

### 01 Welcome / Project launch

Question: does this page now have a real job as a project launch/status console? It should not be a generic landing page. It should help the user understand project readiness, data inputs, workflow status, current result availability, and next action.

### 02 Scenario simulation

Review focus:

- Capacity-range enumeration and specified single-scenario calculation now both exist; check whether the two modes are obvious and safe.
- Batch import now can recognize the down-grid price curve together with load/PV/wind files; check whether the distinction between technical curves and economy price curve is clear.
- Input data curve area and parameter areas do not need equal widths; check whether the current layout supports scanning.
- Input diagnostics should tell the user whether the price curve is recognized and whether fixed price fallback will be used.
- Enumeration should be framed as internal candidate generation, not the product's main result.

### 03 Economy

Review focus:

- Landed load price before/after green power is now displayed; check whether users can understand how fixed-price mode and hourly price-curve mode differ.
- Explain when hourly price curve mode is active.
- Avoid duplicate upload controls for the price curve.
- Keep common economic inputs visible; do not bury key fields behind perspective-specific switches.
- Economy result feedback should make clear whether recommendation seats can now be ranked.

### 04 Recommendation

Review focus:

- Recommendation cards must show why a scenario is useful, not just its ID.
- Scenario cards need capacity text, technical metrics, policy status, and economic metrics.
- Before/after landed load price and down-grid ratio now appear in the UI path; check whether they are placed in the right hierarchy.
- If one scenario wins multiple seats, merge labels rather than duplicate cards.
- Pending/no-candidate seats should be visible and explain why they cannot be ranked.

### 05 Charts

Review focus:

- The policy bottom-margin matrix now includes curtailment rate as a low-priority operational indicator; check whether positive/negative indicators are understandable.
- "容量配置指纹矩阵" has been renamed to "容量配置结构矩阵"; check whether this name works.
- Matrix color bands should not be too harsh.
- Detail chart selection should default to recommended scenarios, while allowing selection of any calculated scenario.
- Quick scenario buttons now switch the selected detail chart; check whether the interaction is obvious.
- Do not hide useful detail charts behind vague "advanced" wording if they are core review artifacts.
- Reconsider whether "方案总览" belongs in the detail chart area or should be absorbed into a scenario selector/status panel.

### 06 Export

Review focus:

- Treat this as a delivery center: selected scenario, report package, technical package, economy table, chart package, simplified report.
- Avoid scattered download buttons across earlier pages.
- Show package readiness: available, needs technical run, needs economy run, needs chart package preparation, pending feature.

## Future Readiness

The website may later go online. UI and underlying presentation-layer design should therefore pay attention to:

- clear page state and routing;
- stable data contracts between UI and services;
- fast enough enumeration and possible parallelization;
- no bloated UI helper logic that makes calculation slower;
- better separation of display data, calculation data, and export data.

## Short Project Instruction To Paste

Act as a senior product manager + UI/UX designer + Streamlit application reviewer for a green direct power / microgrid planning platform. Give specific, implementable UI and interaction recommendations grounded in the project workflow, energy/economy metrics, screenshots, and current Streamlit implementation. Do not suggest changes to core dispatch or calculation口径 unless explicitly marked as a separate future model decision. Prioritize clarity, auditability, professional decision support, and Codex-ready implementation tasks. Distinguish already-implemented-but-needs-polish from new work.
