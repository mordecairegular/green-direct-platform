# Codex 启动提示词

> **状态：讨论稿**
>
> 这是一段可直接复制到 Codex 对话中的启动提示词讨论稿。  
> 正式使用前，应确保项目根目录已经保存 `AGENTS.md`，并在 `docs/` 目录中保存相关 PRD 和契约文档。

---

请在当前项目中执行图表模块 Demo 开发任务。

开始前请先阅读：

- `AGENTS.md`
- `docs/PRD_CHART_MODULE.md`
- `docs/CHART_MODULE_CONTRACT.md`
- `docs/CODEX_TASK_CHART_MODULE.md`
- 当前项目代码结构
- 现有方案计算模块
- 现有 Streamlit UI
- 现有 summary / hourly_detail 输出逻辑

请严格遵守以下原则：

1. 不得重写现有能量平衡、储能 SOC、上网、弃电、下网、站用电等核心计算逻辑。
2. 图表模块只能读取已有计算结果，可以做展示性聚合，但不得重新计算调度逻辑。
3. 新增代码应尽量放在 `modules/visualization/` 下。
4. UI 应接入现有 Streamlit 页面，但不得破坏原有功能。
5. 每个图表函数都应返回 `ChartResult`，包括图对象、图表数据和口径元信息。
6. 缺字段时必须友好提示，不得崩溃。
7. 完成后请运行可行的测试，并说明如何启动、如何验收、修改了哪些文件。

请直接实施一个可运行的 demo 版本。
