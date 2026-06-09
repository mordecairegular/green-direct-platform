# Project Context For ChatGPT Project

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
01 项目启动 / 欢迎页
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

Question: does this page have a real job? If kept, it should not be a generic landing page. It should help the user understand project readiness, data inputs, workflow status, and next action.

### 02 Scenario simulation

Known issues or desired changes:

- Need a function to calculate one specified Wind/PV/BESS configuration, not only capacity-range enumeration.
- Batch import should recognize the down-grid price curve together with load/PV/wind files.
- Input data curve area and parameter areas do not need equal widths; file import can be more compact.
- Input diagnostics should tell the user whether the price curve is recognized and whether fixed price fallback will be used.

### 03 Economy

Known needs:

- Show landed load price before/after green power.
- Explain when hourly price curve mode is active.
- Avoid duplicate upload controls for the price curve.
- Keep common economic inputs visible; do not bury key fields behind perspective-specific switches.

### 04 Recommendation

Known needs:

- Recommendation cards must show why a scenario is useful, not just its ID.
- Scenario cards need capacity text, technical metrics, policy status, and economic metrics.
- Add before/after landed load price and down-grid ratio to recommendation cards.
- If one scenario wins multiple seats, merge labels rather than duplicate cards.

### 05 Charts

Known needs:

- The policy bottom-margin matrix should include curtailment rate as well as green load rate, self-use rate, and export cap.
- "容量配置指纹矩阵" is a strange name; choose a clearer name.
- Matrix color bands should not be too harsh.
- Detail chart selection should default to recommended scenarios, while allowing selection of any calculated scenario.
- Quick scenario cards/buttons should actually switch the selected detail chart.
- Do not hide useful detail charts behind vague "advanced" wording if they are core review artifacts.
- Reconsider whether "方案总览" belongs in the detail chart area or should be absorbed into a scenario selector/status panel.

### 06 Export

Known needs:

- Treat this as a delivery center: selected scenario, report package, technical package, economy table, chart package, simplified report.
- Avoid scattered download buttons across earlier pages.

## Future Readiness

The website may later go online. UI and underlying presentation-layer design should therefore pay attention to:

- clear page state and routing;
- stable data contracts between UI and services;
- fast enough enumeration and possible parallelization;
- no bloated UI helper logic that makes calculation slower;
- better separation of display data, calculation data, and export data.

## Short Project Instruction To Paste

Act as a senior product manager + UI/UX designer + Streamlit application reviewer for a green direct power / microgrid planning platform. Give specific, implementable UI and interaction recommendations grounded in the project workflow, energy/economy metrics, and screenshots. Do not suggest changes to core dispatch or calculation口径 unless explicitly marked as a separate future model decision. Prioritize clarity, auditability, professional decision support, and Codex-ready implementation tasks.
