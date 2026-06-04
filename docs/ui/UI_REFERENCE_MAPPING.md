# UI 参考图到当前项目的映射表

日期：2026-06-03

参考材料：

- 参考图：`docs/ui/reference-dashboard.png`
- GPT 建议：`docs/ui/Codex-UI-重构建议.md`
- 当前代码入口：`src/green_direct/ui/app.py`
- 当前图表入口：`src/green_direct/visualization/chart_ui.py`

## 1. 结论

这张参考图适合作为“工程软件工作台”的信息层级参考，不应作为业务字段或计算口径参考。

可借鉴的是：

- 左侧深蓝导航 + 顶部项目状态栏 + 主工作区；
- 推荐方案卡片优先；
- 多方案横向比较 + 单方案典型日曲线并列；
- 下载与报告集中在底部；
- 底部状态栏显示当前方案、数据路径、版本和帮助入口。

不应照抄的是：

- 图中的示例方案编号；
- 图中的具体数值；
- 图中的收益口径；
- 图中的字段顺序；
- 图中没有经过当前项目代码验证的数据。

## 2. 参考图模块 → 当前项目代码映射

| 参考图区域 | 参考图作用 | 当前项目真实模块 | 当前代码入口 | 可直接借鉴 | 不应照抄 / 注意 |
|---|---|---|---|---|---|
| 左侧深蓝导航栏 | 提供五个主模块入口，当前页高亮 | 欢迎页、方案仿真、经济性测算、方案推荐及图表概览、图表下载和报告生成 | `WORKFLOW_PAGES`、`_render_workflow_navigation()` | 深蓝固定导航、图标+文字、当前模块高亮 | 不要把参数重新塞回侧边栏；侧边栏只做导航和轻量状态 |
| 顶部项目栏 | 展示平台名、项目名、计算状态、数据时间、用户 | 顶部项目状态条 | `_render_project_status_bar()` | 平台名 + 当前项目 + 仿真/经济/推荐状态 + 方案池状态 | 当前项目暂无用户系统，用户/角色只能作为 UI 占位或后续字段 |
| 推荐方案卡片区 | 先让用户看 3-4 个代表方案 | RecommendationPortfolio 推荐组合 | `_render_recommendation_v1()`、`_render_recommendation_cards()` | 排名、推荐标签、方案编号、风光储配置、核心指标、风险提示 | 必须读取推荐引擎输出；不能用图里的固定方案或收益字段 |
| 方案卡片状态标签 | 区分推荐、风险、可查看状态 | 推荐状态、政策状态、风险提示 | `recommendation_status`、`recommendation_reason`、`risk_note` | 成功/警告/风险颜色分层 | 不要把 `no_candidate` 渲染成成功态；无候选要有明确原因 |
| 多方案关键指标对比 | 横向比较代表方案 | 推荐组合 + 用户加入方案的指标比较 | `render_chart_analysis()`、`_render_policy_radar()` | 分组柱状图、方案编号+容量配置图例 | 不要默认画全量枚举；全量表只做高级复核或下载 |
| 典型日运行曲线 | 单方案运行细看 | 典型季节日、关键运行日、全年 8760/8784 曲线 | `_render_operation()`、`select_typical_season_day()` | 图例清楚、单位清楚、负荷/风光/储能/SOC/电网同屏 | 曲线必须读取 `hourly_detail`，不能平滑、插值或重新调度 |
| 下载与报告区 | 把导出动作集中到底部 | 图表下载和报告生成页 | `_render_exports_and_reports_page()` | 三个明确动作：逐小时 CSV、图表 HTML ZIP、简版报告 | 不要把下载按钮散落到仿真、经济、推荐页 |
| 底部状态栏 | 显示当前选中方案、数据路径、版本、帮助 | 当前默认报告方案、数据来源、版本、帮助入口 | `_render_recommendation_bottom_status()` 已部分接入 | 真实方案和数据来源可直接展示 | 版本号、帮助入口、项目数据路径仍待真实 metadata；不得使用样板页占位值 |

## 3. 参考图字段 → 当前项目字段映射

| 参考图字段/文案 | 当前项目对应字段 | 当前来源 | 处理建议 |
|---|---|---|---|
| 推荐席位名称 | `recommendation_labels` | 推荐引擎 V1 | 直接使用，多个席位合并显示 |
| 方案编号 | `scenario_id` | 技术仿真 summary | 直接使用，作为跨模块主键 |
| 光 / 风 / 储 | `pv_capacity`、`wind_capacity`、`bess_power`、`bess_energy` | 技术仿真 summary | 卡片中显示短格式，详情中显示单位 |
| 绿电占比 | `green_load_rate` | 技术仿真 summary | 百分比显示 |
| 自发自用率 | `self_use_rate` | 技术仿真 summary | 百分比显示 |
| 弃电率 | `curtail_rate` | 技术仿真 summary | 百分比显示，风险提示可用 |
| 余电上网比例 / 低上网 | `export_rate` 或 `1 - export_rate` | 技术仿真 summary | 图表中明确是否做“越高越好”转换 |
| 电源侧 FIRR | `firr` | 经济性 V1 电源侧结果 | 已实现时展示；未实现/不可算时显示原因 |
| 同一主体 FIRR | `single_entity_firr_pre_tax` | 同一主体税前经济性结果 | 展示时必须注明税前口径 |
| 负荷侧收益 | `load_side_annual_benefit` | 推荐引擎负荷侧明细 | 只在可成交席位中作为关键指标 |
| 风险提示 | `risk_note`、`recommendation_reason`、`fail_reasons` | 推荐结果和技术结果 | 卡片底部展示简短提示；完整原因进明细 |
| 24H 典型日日期 | `select_typical_season_day().label` | 图表选日逻辑 | 必须显示 `MM/DD` |
| 逐小时曲线 | `hourly_detail` 中负荷、光伏、风电、储能、电网、SOC 字段 | 单方案逐小时台账 | 只读展示，不重算 |

## 4. 页面职责映射

| 页面 | 是否保留计算入口 | 是否默认展示图表 | 是否默认展示下载 | 样板页借鉴重点 |
|---|---:|---:|---:|---|
| 欢迎页 | 否 | 否 | 否 | 项目状态、下一步入口、轻量概览 |
| 方案仿真 | 是，技术仿真入口 | 否 | 否 | 数据曲线、候选方案池、政策约束分区 |
| 经济性测算 | 是，经济性 V1 入口 | 否 | 否 | 经济参数分层、复核表折叠 |
| 方案推荐及图表概览 | 否，读取已有结果 | 是 | 否 | 推荐卡片 + 多方案对比 + 典型日曲线 |
| 图表下载和报告生成 | 否，读取已有结果 | 可预览/可导出 | 是 | 下载动作集中、报告生成、底部状态 |

## 5. 样板页边界

本轮样板页只放在 `docs/ui/recommendation_dashboard_sample.html`，作为静态 UI 参考，不接入 Streamlit，不调用核心计算，不写入真实结果。

样板页允许使用 mock 数据，但必须满足：

- 明确标注为 UI demo；
- 字段名来自当前项目真实字段；
- 不新增业务口径；
- 不影响 `src/green_direct/` 中的技术仿真、储能调度、经济性计算；
- 后续如要落地到 Streamlit，应按本映射表逐项替换现有组件。

## 6. 样板页区块 → 正式 Streamlit 页面详细映射

本表用于把 `docs/ui/recommendation_dashboard_sample.html` 的视觉区块映射到当前 Streamlit 工作台真实入口。样板页只提供布局、密度和视觉层级参考；正式页面只能读取当前 session state、技术仿真结果、经济性结果、推荐结果和逐小时明细，不得把样板页中的 mock 数值搬入正式链路。

| UI 区块 | 样板页展示内容 | 正式 Streamlit 对应位置/函数 | 真实数据来源 | 真实字段名 | 单位 | 当前是否已实现 | 是否仍为 mock | 缺失项 | 处理方式 |
|---|---|---|---|---|---|---|---|---|---|
| 顶部状态栏 | 平台/项目状态、当前模块、计算状态、方案池状态 | `_render_project_status_bar()` | `WORKFLOW_PAGE_META`、`st.session_state["batch_result"]`、`st.session_state["economy_v1_result"]`、工作流完成状态 | `scenario_id`、`pass_policy`、`summary` | 个、状态 | 已实现 | 否 | 真实项目名称、项目编号、建设地点等项目元数据尚未结构化 | 保留轻量顶部状态条；只展示已有计算状态和方案池数量，真实项目字段等数据模型稳定后再接入 |
| 顶部状态栏 | 数据时间范围 | `_render_project_status_bar()`、`_data_range_status()` | `batch_result.hourly_details` 中首个带时间戳的逐小时明细 | `hourly_detail`、`timestamp` | 日期/小时 | 已实现 | 否 | 多数据源项目元数据尚未结构化 | 从真实逐小时明细推导起止时间和小时数；无明细时显示“待仿真”，不使用样板页固定日期 |
| 顶部状态栏 | 当前用户或角色 | 当前正式页无用户系统 | 无 | 无 | 无 | 未实现 | 样板页是，正式页否 | 用户、角色、权限来源缺失 | 仅作为 UI 样板保留在 `docs/ui/`；正式页不显示虚构用户 |
| 推荐方案卡片 | 推荐排序、推荐席位、方案编号 | `_render_recommendation_v1()`、`_render_recommendation_cards()` | `build_recommendation_study(...).portfolio`、技术 `summary`、经济性汇总 | `scenario_id`、`recommendation_labels`、`recommendation_status` | 序号、文本、状态 | 已实现 | 否 | 推荐排序的视觉编号可继续加强 | 使用推荐引擎输出的代表方案组合；同一方案命中多个席位时合并标签，不回到全量枚举卡片 |
| 推荐方案卡片 | 光伏、风电、储能配置 | `_render_recommendation_cards()`、`_capacity_config_text()` | 推荐组合合并后的技术 `summary` 行 | `pv_capacity`、`wind_capacity`、`bess_power`、`bess_energy` | 万kW、万kWh | 已实现 | 否 | 无 | 卡片首屏保留短配置，详情或导出中保留完整字段和单位 |
| 推荐方案卡片 | 绿电占比、自发自用率、弃电率、余电上网比例 | `_render_recommendation_cards()`、`_render_recommendation_v1()` | 技术仿真 `summary` 和推荐组合 `portfolio` | `green_load_rate`、`self_use_rate`、`curtail_rate`、`export_rate` | % | 已实现 | 否 | 无 | 不改计算口径；卡片直接读取 `export_rate`，并明确是上网比例 |
| 推荐方案卡片 | 经济性指标或节费指标 | `_render_recommendation_cards()`、`_render_recommendation_v1()` | `st.session_state["economy_v1_result"]`、`st.session_state["single_entity_economy_result"]`、推荐结果中的负荷侧明细 | `firr`、`single_entity_firr_pre_tax`、`load_side_annual_benefit` | %、万元/年 | 已实现 | 否 | 缺少经济性测算时只能展示不可用状态 | 经济性未运行时显示待测算或不可排序原因；不伪造收益数值 |
| 推荐方案卡片 | 推荐理由、风险提示 | `_render_recommendation_cards()` | 推荐引擎输出 | `recommendation_reason`、`risk_note`、`fail_reasons` | 文本 | 已实现 | 否 | 风险提示的分级和展开详情可继续优化 | 卡片只放短提示，完整原因留在推荐详情、表格或导出中 |
| 多方案关键指标对比图 | 代表方案之间的绿电、自用、低弃电、低上网对比 | `render_chart_analysis()`、`_render_policy_radar()` | 推荐组合 `portfolio`、用户加入的方案、技术 `summary` | `scenario_id`、`green_load_rate`、`self_use_rate`、`curtail_rate`、`export_rate`、`pv_capacity`、`wind_capacity`、`bess_power`、`bess_energy` | %、万kW、万kWh | 已实现 | 否 | 图表标题和图例仍可继续贴近样板页 | 只围绕代表方案和用户加入方案绘图；`curtail_rate` 和 `export_rate` 在“低弃电/低上网”视角下做展示性反向，不改变源字段 |
| 多方案关键指标对比图 | 方案图例显示编号和风光储配置 | `render_chart_analysis()`、`_scenario_with_capacity_label()` | 技术 `summary` 中每个 `scenario_id` 的配置 | `scenario_id`、`pv_capacity`、`wind_capacity`、`bess_power`、`bess_energy` | 文本、万kW、万kWh | 已实现 | 否 | 无 | 保持图例同时显示方案编号和容量配置，避免只有编号导致不可读 |
| 24H 典型日运行曲线 | 负荷、光伏、风电、储能充放电、电网交换、弃电、SOC | `render_chart_analysis()`、`_render_operation()`、`_render_day_operation_chart()` | `batch_result.hourly_details[scenario_id]`，经 `adapt_hourly()` 标准化后只读绘图 | `hourly_detail`、`timestamp`、`load_power`、`pv_generation_power`、`wind_generation_power`、`bess_charge_power`、`bess_discharge_power`、`grid_import_power`、`grid_export_power`、`curtail_power`、`soc_end` | 万kW、SOC | 已实现 | 否 | 无 | 图表模块只读取逐小时台账，不平滑、不插值、不重新调度 |
| 24H 典型日运行曲线 | 四季典型日显示具体 MM/DD | `select_typical_season_day()`、`_render_operation()` | 逐小时明细中的时间戳和季节中心日法选日结果 | `hourly_detail`、`timestamp`、`label` | MM/DD | 已实现 | 否 | 无 | 保持季节中心日法和 `MM/DD` 标签；样板页日期不得覆盖真实选日结果 |
| 下载与报告区 | 逐小时 CSV、方案汇总、全部逐小时 ZIP | `_render_recommendation_export_handoff()`、`_render_exports_and_reports_page()` | `batch_result.summary`、`batch_result.hourly_details`、`config_snapshot` | `scenario_id`、`hourly_detail`、`summary` | CSV、ZIP、Excel | 已实现 | 否 | 无 | 推荐页只给出默认报告方案和进入下载页按钮；真实下载动作集中在最后一个页面 |
| 下载与报告区 | 图表 HTML/ZIP 下载 | `_render_exports_and_reports_page()`、`_build_chart_html_zip()` | 所选方案逐小时明细、推荐组合范围、技术 `summary` | `scenario_id`、`hourly_detail`、`green_load_rate`、`self_use_rate`、`curtail_rate`、`export_rate` | HTML、ZIP | 已实现 | 否 | PNG 批量导出尚未接入 | HTML 图表可下载；PNG 依赖后续浏览器或 kaleido 环境，先明确为空缺 |
| 下载与报告区 | 经济性汇总、推荐组合、简版报告 | `_render_exports_and_reports_page()`、`_build_simple_report_markdown()` | `economy_v1_result`、`single_entity_economy_result`、推荐引擎重新构建的导出结果 | `scenario_id`、`recommendation_labels`、`recommendation_reason`、`risk_note`、`firr`、`single_entity_firr_pre_tax`、`load_side_annual_benefit` | Excel、Markdown、%、万元/年 | 已实现 | 否 | 未运行经济性或推荐输入缺失时部分导出不可用 | 显示真实可用下载；缺失时提示“暂不可用/待测算”，不补 mock 报告 |
| 底部状态栏 | 当前选中方案、数据来源、版本号、帮助入口 | `_render_recommendation_bottom_status()` | 推荐组合默认报告方案、`batch_result.hourly_details`、session 中的经济性结果 | `scenario_id`、`hourly_detail` | 文本 | 部分实现 | 仅样板页仍为 mock，正式页否 | 真实版本号、帮助入口和项目数据路径尚未结构化 | 正式页只显示真实默认报告方案和数据来源；版本号、帮助入口显示“待接入”，不显示虚构值 |

## 7. 本次吸收边界

- 吸收样板页的信息层级、紧凑布局和“代表方案优先”的方法论，不照搬 React/FastAPI 式目录或后台架构。
- `docs/ui/recommendation_dashboard_sample.html` 只作为静态视觉参考，mock 数据只能存在于 `docs/ui/`。
- 正式 Streamlit 页面只接真实字段、真实计算结果和真实导出，不把样板页数值、项目用户、版本号或底部状态栏占位直接搬进正式页面。
- 缺失数据统一显示为空状态、待测算、待接入或暂不可用，不用 mock 数据补齐。
- 下一步若进入代码接入阶段，建议只收敛在“方案推荐及图表概览”和“图表下载和报告生成”相关函数，不做全站重构。
