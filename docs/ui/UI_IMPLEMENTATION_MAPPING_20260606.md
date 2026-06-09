# UI Implementation Mapping - 2026-06-06

本文件记录本轮正式 Streamlit UI 落地时，原型区块如何映射到当前底层功能。原则是：先改工作台外壳和任务分层，不删除底层输入能力，不改变技术仿真、经济性、推荐或图表计算口径。

## Scope

本轮正式代码只改：

- `src/green_direct/ui/app.py` 的展示层、页面标题、首屏任务台、按钮入口和说明文案；
- 不改 `core`、`batch`、`economy`、`recommendation`、`services`、`visualization` 的底层计算逻辑；
- 不改既有输入控件 key，不改 `run_technical_study()`、`run_economic_study()`、`build_recommendation_study()` 的参数含义。

## Page 01 - Project Launch

正式页面 key 仍是 `欢迎页`，用于兼容旧 session 和测试；用户看到的标题改为 `项目启动台`。

| 原型区块 | 正式实现 | 真实数据来源 | 是否改计算 |
|---|---|---|---|
| 输入准备 | `_render_welcome_page()` 中 `输入准备` 卡片 | `curve_metric_snapshot`、项目级电价曲线 state、`batch_result.hourly_details` | 否 |
| 候选方案池 | `_render_welcome_page()` 中 `候选方案池` 卡片 | `batch_result.scenario_count`、`batch_result.summary.pass_policy`、技术指标列 | 否 |
| 推荐状态 | `_render_welcome_page()` 中 `推荐状态` 卡片 | `economy_v1_result`、`recommendation_v1_inputs`、推荐结果只读构建 | 否 |
| 交付准备 | `_render_welcome_page()` 中 `交付准备` 卡片 | `batch_result`、`economy_v1_result`、工作流状态 | 否 |
| 下一步建议 | `_launch_next_steps()` | 当前 session 中是否已有技术/经济/推荐结果 | 否 |
| 项目边界 | `_render_welcome_page()` 静态边界表 | AGENTS/产品原则和当前实现状态 | 否 |

## Page 02 - Simulation

本轮未重排底层输入表单，只加了任务边界说明。2026-06-08 补充：批量上传入口已能同时分拣项目级下网电价曲线。

保留的正式能力：

- 批量上传三条技术 CSV；
- 批量上传中可选加入项目级下网电价曲线 CSV/XLSX；
- 单独上传覆盖；
- 自动列识别和人工列选择；
- 曲线状态卡；
- 项目级下网电价曲线上传；
- 光伏、风电、储能功率范围；
- 是否包含无储能方案；
- 储能时长；
- 方案数提醒阈值；
- 允许上网、年度上网比例硬约束；
- 自发自用率、绿电占用电比例、上网比例约束；
- 电网交换功率限制；
- SOC、效率、循环寿命、日历寿命；
- Demo 生成和正式测算。

这些控件的 key 仍来自 `SIMULATION_WIDGET_STATE_KEYS` 或已有上传 key。外层视觉说明不参与 `TechnicalStudyInput` 构造。

电价曲线映射边界：

- 技术曲线仍只进入 `run_technical_study()`，且当前批量技术曲线只支持 CSV；
- 下网电价曲线进入 `project_price_curve_data` / `project_price_curve_meta`；
- 下网电价曲线只影响后续经济性测算和推荐排序，不改变技术调度；
- 若批量上传中同时出现多个下网电价曲线文件，只使用第一个并提示忽略后续文件；
- 若误把技术曲线 XLSX 放入批量上传，页面提示技术曲线当前仅支持 CSV。

## Page 03 - Economy

本轮新增首屏经济任务台，但原参数工作台完整保留。

| 原型区块 | 正式实现 | 底层映射 |
|---|---|---|
| 技术结果 | `_render_economy_task_overview()` | 读取 `summary`、`batch_result` |
| 经济执行 | `_render_economy_task_overview()` | 读取 `price_mode`、项目级电价曲线 state、`recommendation_v1_inputs` |
| 结果回馈 | `_render_economy_task_overview()` | 读取 `economy_v1_result.summary` 和 `single_entity_economy_result.summary` |
| 首屏计算按钮 | `run_economy_v1_top` | 与底部 `run_economy_v1_all` 共用同一段 `run_economic_study()` 分支 |
| 参数工作台 | `_render_economy_v1()` 原有 expander | 原字段、原控件、原参数对象继续保留 |

保留的经济输入能力：

- 运营期、折现率、最低可接受 FIRR；
- Year 0 建设投资；
- 运行成本；
- 储能更换；
- 上网电价、绿电结算价、外部购电净成本、环境价值；
- 税率；
- 其他经营收入；
- 电费清单组价；
- 负荷侧可减少购网费用覆盖；
- 项目级下网电价曲线自动读取。

2026-06-08 补充：

- 经济性页不新增二次电价曲线上传入口，继续只读使用项目级曲线；
- `economy_v1_result` 现在保存 `price_curve_diagnostics`；
- 若曲线和逐小时台账发生 timestamp / hour_index / 行序对齐告警，经济性页展示“价格曲线对齐诊断”。

## Page 04-06

方案推荐、图表概览和导出页本轮继承前一轮结构，并在 2026-06-08 对图表概览做展示层调整：

- 推荐页仍集中展示推荐席位、理由、风险和明细；
- 图表页仍围绕推荐组合和用户指定方案；
- 图表概览主图从普通柱状图调整为“政策底线余量矩阵”和“容量配置指纹矩阵”；
- 典型日、能量流向和完整图表复核不再藏在高级折叠区；
- 图表复核中的方案选择由图表概览页统一控制，`render_chart_analysis()` 可接收外部 `selected_scenario_ids` / `active_scenario_id`；
- 嵌入图表复核时默认不再重复展示“方案总览”页签；
- 导出页仍集中管理技术、图表、经济和报告下载。

2026-06-08 追加：

- 政策矩阵补入弃电率列；弃电率当前按“低优运行指标”展示，不新增或伪造技术仿真政策阈值；
- 容量主图命名改为“容量配置结构矩阵”，并降低色带饱和度；
- 图表概览页的详细图表选择改为“全部已计算方案”下拉框，默认推荐方案，但可直接选择任一方案；
- 方案选择区和详细复核区都展示方案编号与风光储配置文字；
- 嵌入 `render_chart_analysis()` 时关闭旧 hero，页面不再出现“图表分析：方案图谱”。

## Guardrails For Next Iteration

- 不要为了让 02/03 更像原型而删除“高级”输入控件；先做分组、摘要和折叠层级。
- 任何输入控件移动前，先确认对应 key、默认值、`_stored_widget_value()` 和最终参数对象字段。
- 新增按钮可以复用已有计算分支；不要复制一套新的经济或技术计算逻辑。
- 推荐和图表 UI 可小范围试用后逐步改，但推荐排序和图表数据来源必须继续读取正式结果。
- 若拆文件，先搬 UI 渲染函数，不搬计算和服务调用。

## Verification

本轮验证：

```bash
python -m py_compile src/green_direct/ui/app.py
python -m pytest tests/test_ui_import.py
python -m pytest tests/test_visualization_smoke.py tests/test_chart_data.py
```

浏览器取证：

- `docs/ui/audit-20260606-product-design/screenshots/39-streamlit-01-project-launch.png`
- `docs/ui/audit-20260606-product-design/screenshots/40-streamlit-02-simulation-guardrail.png`
- `docs/ui/audit-20260606-product-design/screenshots/42-streamlit-03-economy-overview-after-demo.png`
- `docs/ui/audit-20260606-product-design/screenshots/43-streamlit-03-economy-after-top-run.png`
