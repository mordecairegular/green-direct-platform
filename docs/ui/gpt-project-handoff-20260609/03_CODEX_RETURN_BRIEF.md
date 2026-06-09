# Prompt Template To Bring ChatGPT Project Output Back To Codex

When ChatGPT Project produces UI review results, paste the results into Codex with the following instruction.

```text
请基于下面这份 ChatGPT Project UI 评审结果继续在本仓库落地。

硬约束：
1. 不要改核心技术仿真、储能调度、政策计算和既有经济计算口径，除非任务明确说“只新增展示字段/服务层汇总字段，不改变算法”。
2. 如果需要新增字段，优先在服务层做汇总/派生，保持与 scenario_id 关联，不在 UI 中偷偷重算核心口径。
3. UI 改动优先集中在：
   - src/green_direct/ui/app.py
   - src/green_direct/visualization/chart_ui.py
   - 必要的展示层 helper / tests / docs
4. 必须保护已有测试。至少运行：
   - python -m pytest tests/test_ui_import.py
   - python -m pytest tests/test_visualization_smoke.py tests/test_chart_data.py
   - 若涉及经济/价格字段：python -m pytest tests/test_price_curves.py tests/test_study_runner.py
5. 完成后更新 notes/PRODUCT_POLISH_LOG.md。
6. 用浏览器实际验收 Demo -> 经济测算 -> 推荐 -> 图表概览 -> 导出中心。

请先自查当前代码，再把 UI 评审结果拆成最小可交付阶段。若存在会触及核心算法的问题，先标记为“需要确认”，不要擅自改。

下面是 ChatGPT Project 输出：

[粘贴 ChatGPT Project 的“给 Codex 的具体修改任务”和关键设计结论]
```

## Recommended Codex Acceptance Checklist

For the next Codex implementation round, ask Codex to report:

- changed files;
- whether core algorithm files were untouched or only read;
- how the UI now handles 01 welcome / project launch;
- how 02 handles batch import plus specified single scenario;
- how 03/04/05 show landed load price before and after green power;
- how 05 chart selector and scenario quick cards interact;
- how export/download actions stay centralized in the delivery center;
- what tests and browser checks passed;
- remaining questions for the next UI review loop.
