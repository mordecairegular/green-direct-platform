# 迁移与软件打磨计划

日期：2026-05-19  
状态：后续开发路线草案  
目标：指导项目从 V0.1 技术测算工具平稳演进为方案策划与推荐平台

## 1. 总体判断

继续使用当前项目文件夹是合适的，因为这里已经沉淀了：

- 可运行的 V0.1 风光储技术内核；
- 测试用例；
- 数据读取与导出链路；
- Streamlit UI；
- 图表模块；
- 产品打磨记录；
- 软件接口说明；
- 软著申请材料。

但继续使用的前提是：必须更新约束文档和架构文档，避免后续 Codex 或 Claude Code 继续被“V0.1 only、不做经济性、不做柴发”的旧边界限制。

本轮已将：

- `AGENTS.md`
- `CLAUDE.md`

从旧 V0.1 指令升级为新产品方向指令。

旧文档不删除，而是作为 V0.1 基线和回归参考保留。

## 2. 当前沉淀资产如何使用

### 2.1 应保留为基线的内容

以下内容继续有价值：

- `ALGORITHM_SPEC.md`：风光储逐小时基线算法；
- `TEST_CASES.md`：核心行为测试；
- `OUTPUT_SCHEMA.md`：当前导出字段；
- `docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`：当前接口基线；
- `notes/PRODUCT_POLISH_LOG.md`：已讨论过的产品口径与经验；
- `src/green_direct/core/`：现有技术内核；
- `tests/`：回归测试。

这些内容不再限制未来产品边界，但仍用于回答：

```text
现有风光储基线是否被破坏？
```

### 2.2 应降级为历史约束的内容

以下旧约束不再作为未来开发硬边界：

- 只实现 V0.1；
- 不做经济性；
- 不考虑柴油发电；
- 不考虑离网；
- 结果主流程围绕全量枚举表。

新的方向是：

```text
保留技术基线，扩展为项目方案推荐平台。
```

### 2.3 PRODUCT_POLISH_LOG 的参考价值

`notes/PRODUCT_POLISH_LOG.md` 中最值得继续继承的经验：

- 用户不应被内部编码困扰，例如储能时长 `0` 应转译为“包含无储能方案”；
- 输入数据应自动识别，但保留人工覆盖；
- 长耗时任务必须有进度反馈；
- 数据状态与质量提示是技术软件的核心体验；
- 风光负值可能是业务口径，不一定是异常；
- 站用电口径必须明确；
- 电网交换功率限制需要同时记录限制带来的代价；
- 大批量计算要区分“汇总筛选数据”和“单方案复核明细”；
- 下载和导出应使用稳定数据载体；
- 软件接口文档应从过程日志中提炼出来。

这些经验应进入后续架构，而不是只停留在 UI 打磨层面。

## 3. 分阶段迁移路线

### 阶段 0：文档重定向与开发规则更新

状态：本轮进行中。

目标：

- 更新 `AGENTS.md`；
- 更新 `CLAUDE.md`；
- 新增专家审查材料；
- 明确旧 V0.1 文档是基线，不是未来边界；
- 明确经济性排序、柴发、推荐引擎进入后续范围。

完成标准：

- 后续 Codex / Claude Code 读取项目规则时，不会继续认为“只能做 V0.1”；
- 专家可以通过 `notes/architecture_reframe_20260519/` 理解项目现状和目标。

### 阶段 1：结构化输入诊断

目标：

把当前异常字符串和 warning list 升级为结构化诊断对象。

建议新增：

```text
src/green_direct/domain/diagnostics.py
src/green_direct/services/input_auditor.py
```

建议对象：

```text
DiagnosticIssue
InputDiagnostics
```

第一阶段不必改完所有读取逻辑，可以先包一层，把已有错误转换为统一结构。

测试重点：

- 行数不合法；
- 时间戳不一致；
- 缺列；
- 负荷负值；
- 光伏 / 风电大于 1；
- 大批量方案数量过大；
- 经济参数缺失但需要经济排序。

用户价值：

- UI 能显示“阻断 / 警告 / 提示”；
- 报告能附带输入审查；
- 专家能快速定位数据问题。

### 阶段 2：统一 EnergyLedger 与 StudyResult

目标：

把当前逐小时明细升级为更明确的能源台账，并建立顶层 `StudyResult`。

建议新增：

```text
src/green_direct/domain/ledger.py
src/green_direct/domain/study.py
src/green_direct/services/study_runner.py
```

迁移方式：

1. 不立刻重写现有 `run_single_scenario`；
2. 先定义 `HourlyEnergyLedger` 字段标准；
3. 让现有 hourly_detail 可以适配为 ledger；
4. `StudyRunner` 初期内部仍调用 `run_batch`；
5. 输出 `StudyResult` 包装 `BatchResult`、diagnostics 和 config。

当前落地状态（2026-06-04）：

- 已在 `src/green_direct/services/study_runner.py` 定义 `TechnicalStudyInput`、`TechnicalStudyResult`、`StudyResult` 和 `run_technical_study()`；
- `run_technical_study()` 已按迁移方式第 4、5 点先包装现有 `read_curve_set()` / `run_batch()`，并输出配置快照和结构化输入诊断；
- `HourlyEnergyLedger` 字段标准仍沿用现有 hourly_detail，尚未单独抽出 `domain/ledger.py`；图表、推荐和导出页仍保留 `batch_result` 兼容读取，后续逐步迁移到 `StudyResult`。

好处：

- UI、图表、报告不再直接依赖底层 batch 结构；
- 后续推荐、经济性、柴发扩展有统一事实表；
- 大批量按需明细更容易实现。

### 阶段 3：推荐引擎

目标：

让系统主输出从“全部枚举结果表”转为“推荐方案组合”。

建议新增：

```text
src/green_direct/recommendation/filters.py
src/green_direct/recommendation/ranker.py
src/green_direct/recommendation/selector.py
src/green_direct/recommendation/models.py
```

初期输入：

- 当前 `summary`；
- `PolicyParams`；
- 可选经济结果。

初期输出：

```text
RecommendationPortfolio
RecommendedScenario
```

第一批推荐标签：

- 推荐综合方案；
- 政策达标且低弃电方案；
- 高绿电占比方案；
- 高自发自用方案；
- 低储能容量方案；
- 低下网比例方案；
- 用户指定对照方案。

如果经济性已实现，则增加：

- 年净成本最低方案；
- 投资最低方案；
- LCOE-like 最低方案。

测试重点：

- 不达标方案不能被标为推荐综合方案；
- 同一方案命中多个标签时去重；
- 推荐理由不为空；
- 所有推荐方案都能找到对应 `scenario_id`。

### 阶段 4：轻量经济性排序

目标：

先满足“基于经济性排序推荐方案”，不急于做完整财务模型。

建议新增或完善：

```text
src/green_direct/economy/cost_inputs.py
src/green_direct/economy/economic_evaluator.py
src/green_direct/economy/ranking_metrics.py
```

建议输入：

```text
pv_capex_per_kw
wind_capex_per_kw
bess_power_capex_per_kw
bess_energy_capex_per_kwh
diesel_capex_per_kw
grid_connection_cost
fixed_om_rates
grid_purchase_price
export_price
diesel_fuel_price
diesel_fuel_consumption_rate
```

建议输出：

```text
capex_total
annual_om_cost
grid_purchase_cost
diesel_fuel_cost
export_revenue
annual_net_cost
lcoe_like
simple_payback
```

重要边界：

- 经济性评价读取技术 summary / ledger；
- 不改变调度；
- 通过 `scenario_id` 关联；
- 经济性参数不完整时输出 warning，不要悄悄用不可信默认值。

测试重点：

- 成本分项计算；
- 经济性结果不改变技术 summary；
- 缺少关键价格参数时有诊断；
- 推荐引擎能使用经济性排序。

### 阶段 5：柴发与离网模式

目标：

在统一台账和调度策略基础上加入柴发，适配离网和并网加备用。

建议新增：

```text
src/green_direct/domain/assets.py
src/green_direct/engine/dispatch_strategies.py
src/green_direct/engine/diesel_dispatch.py
```

初期柴油模型：

```text
capacity
min_output
fuel_liter_per_kwh
fuel_price
variable_om_cost
emission_factor
```

初期离网策略建议：

```text
新能源供负荷
-> 富余新能源充储能
-> 富余弃电
-> 新能源不足时储能放电
-> 柴发补足剩余缺口
-> 柴发不足则记录 unserved_load
```

初期并网加柴发策略建议：

```text
新能源供负荷
-> 储能放电
-> 电网下网
-> 电网受限或不可用时柴发补足
-> 仍不足则记录 unserved_load
```

暂缓项：

- 柴发启停优化；
- 最小运行时间；
- 爬坡约束；
- 经济最优调度；
- 柴发给储能充电；
- 储能内部绿电 / 非绿电分账。

这些可以在专家确认后逐步加入。

测试重点：

- 柴发发电不计入新能源发电；
- 柴发发电不计入绿电自发自用；
- 柴发功率不超过容量；
- 柴发不足时记录缺供；
- 离网模式下不出现电网下网；
- 并网加柴发模式下柴发仅在策略允许时运行。

### 阶段 6：大批量模式与 ResultStore

目标：

解决大规模枚举时的内存和 UI 卡顿问题。

建议：

```text
summary 常驻内存
selected hourly ledger 常驻内存
all hourly ledger 按需保存 / 按需重算
```

建议新增：

```text
src/green_direct/services/result_store.py
```

输出目录建议：

```text
outputs/runs/{study_id}/
  config_snapshot.json
  diagnostics.json
  summary.csv
  policy_results.csv
  economic_results.csv
  recommendations.json
  hourly/
    {scenario_id}.csv
```

测试重点：

- summary 和按需 hourly 的容量参数一致；
- 推荐方案能加载到逐小时台账；
- 导出报告不依赖全量 hourly 已在内存中。

### 阶段 7：UI、图表和报告重塑

目标：

在架构稳定后再打磨 UI。

主界面应围绕：

- 输入审查；
- 方案数量和运行状态；
- 推荐方案组合；
- 当前选中方案；
- 方案对比；
- 图表；
- 报告和导出。

不建议继续把巨大汇总表作为第一屏核心。

报告初期可输出：

- 项目输入摘要；
- 输入审查结果；
- 推荐方案表；
- 方案技术指标；
- 方案经济性指标；
- 典型日 / 年度时序图；
- 能量流向；
- 不达标原因；
- 逐小时明细附件。

## 4. 新旧文档关系

### 4.1 当前有效开发规则

- `AGENTS.md`
- `CLAUDE.md`
- `notes/architecture_reframe_20260519/`
- `notes/architecture_reframe_20260519/04_HOURLY_DISPATCH_LOGIC_WITH_DIESEL.md`

### 4.2 当前接口基线

- `docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`
- `notes/PRODUCT_POLISH_LOG.md`

### 4.3 V0.1 历史基线

- `PRD.md`
- `ALGORITHM_SPEC.md`
- `DATA_SCHEMA.md`
- `OUTPUT_SCHEMA.md`
- `TEST_CASES.md`
- `UI_SPEC.md`
- `ECONOMY_EXTENSION_SPEC.md`

这些文档不删除，但后续应在引用时说明它们的角色是“V0.1 基线”。

## 5. 后续开发对 Codex / Claude Code 的要求

建议每次新任务都明确：

```text
本次是文档、架构、测试、核心算法、经济性、柴发、推荐、UI 中的哪一类？
是否允许改动现有 V0.1 调度口径？
是否需要运行 pytest？
是否需要更新专家审查文档？
```

AI 协作时应遵守：

- 不要一次性大重构；
- 不要删除旧测试；
- 不要删除旧文档；
- 新增调度口径必须命名；
- 经济性不能悄悄改变技术调度；
- 柴发不能混入电网下网字段；
- 非新能源进入储能后，必须防止绿电口径污染；
- 推荐方案必须有解释理由；
- 大批量计算要考虑内存和按需明细。

## 6. 专家审查建议议程

建议请专家按以下顺序审查：

1. 软件定位是否合理；
2. 当前 V0.1 计算口径是否有明显问题；
3. 新目标架构是否过度设计或缺少关键模块；
4. 经济性排序第一阶段应纳入哪些指标；
5. 柴发初期模型和调度策略应如何定；
6. 离网可靠性指标应如何表达；
7. 推荐方案类别和排序逻辑是否符合工程决策；
8. 哪些测试用例必须新增；
9. 哪些功能应暂缓。

## 7. 近期最小可执行任务建议

如果专家审查前仍想继续开发，建议只做低风险骨架任务：

1. 新增 `domain/diagnostics.py`，定义 `DiagnosticIssue`；
2. 新增 `recommendation/models.py`，定义 `RecommendedScenario` 和 `RecommendationPortfolio`；
3. 新增 `services/study_runner.py`，先包装现有 `run_batch`；
4. 新增推荐引擎的纯 summary 选择逻辑；
5. 不急着改核心调度；
6. 不急着加柴发；
7. 不急着重做 UI。

这样即使后续专家提出调整，也不会浪费太多实现成本。

## 8. 风险清单

| 风险 | 说明 | 建议 |
|---|---|---|
| 旧文档误导后续开发 | 旧文档强调 V0.1 only | 已更新 AGENTS/CLAUDE，并新增本目录文档 |
| 一次性大重构 | 容易打坏现有可运行基线 | 小步迁移，保持测试通过 |
| 经济性过早复杂化 | 税费、融资、折旧会拖慢主线 | 先做轻量排序 |
| 柴发调度口径不清 | 影响离网可靠性和绿电指标 | 先请专家确认调度策略 |
| 储能来源混淆 | 柴发/电网充电后可能污染绿电口径 | 初期禁止非新能源充储，或做来源分账 |
| 大批量内存压力 | 保存所有小时明细会很重 | summary 优先，明细按需 |
| 推荐黑箱化 | 用户不信任综合评分 | 推荐理由和 trade-off 必须可见 |

## 9. 阶段验收建议

每个阶段完成时至少检查：

- 是否破坏现有 pytest；
- 是否更新相关文档；
- 是否保留旧基线；
- 是否新增必要测试；
- 是否有用户可理解的错误或诊断；
- 是否能追溯每个推荐方案来自哪个 `scenario_id`；
- 是否能为选中方案提供逐小时复核明细。
