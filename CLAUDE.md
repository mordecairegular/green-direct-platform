# CLAUDE.md

## 项目定位

本项目正在从“绿电直连风光储多方案批量测算软件”升级为“绿电直连 / 微电网项目方案策划与推荐平台”。

当前代码中的 V0.1 风光储技术测算模块是重要基线，应保留其算法价值、测试资产和接口资料。但它不再是最终产品边界。后续允许围绕以下方向演进：

- 方案筛选与代表方案推荐；
- 轻量经济性排序；
- 柴油发电机组；
- 离网、并网、并网加备用电源等项目模式；
- 统一逐小时能源台账；
- 面向报告和专家复核的输出。

## 必读文档

开始架构或功能开发前，优先阅读：

- `CLAUDE.md`
- `AGENTS.md`
- `notes/HANDOFF_FOR_NEW_MACHINE.md`
- `notes/architecture_reframe_20260519/01_EXPERT_REVIEW_BRIEF.md`
- `notes/architecture_reframe_20260519/02_TARGET_ARCHITECTURE_AND_CALCULATION_LOGIC.md`
- `notes/architecture_reframe_20260519/03_MIGRATION_AND_POLISH_PLAN.md`
- `notes/architecture_reframe_20260519/04_HOURLY_DISPATCH_LOGIC_WITH_DIESEL.md`
- `docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`
- `notes/PRODUCT_POLISH_LOG.md`

修改现有 V0.1 风光储技术计算逻辑前，还必须阅读：

- `ALGORITHM_SPEC.md`
- `TEST_CASES.md`
- `OUTPUT_SCHEMA.md`

## 核心原则

1. 算法正确性和可复核性优先于界面美观。
2. 当前 V0.1 计算口径是回归基线，不应被无意破坏。
3. 枚举是内部搜索手段，不应把全量枚举表作为主要用户结果。
4. 主要输出应逐步转为代表方案组合、推荐理由、关键指标和可审查明细。
5. 图表、报告、经济性、推荐层应读取技术仿真结果，不应私自重算或改变调度结果。
6. 经济性排序可以进入近期范围，但应先作为筛选和排序层，不要一开始强行做完整财务模型。
7. 柴发可以进入方案逻辑，但必须作为明确资产和明确调度策略建模，不要混入电网购电字段。
8. 如果引入新的调度策略，应命名并文档化，例如并网优先、柴发备用、离网柴发兜底等。
9. 对人工复核重要的数据必须保留逐小时明细或可按需再生成。
10. 每次修改核心算法后必须运行 `pytest`。
11. 不要删除旧文档。旧 V0.1 文档应作为基线参考保留。
12. 当前图表模块只是早期原型，效果不理想，不应作为近期重点或不可替换资产。

## 当前基线规则

在现有风光储贪心调度策略下：

- 储能只能从富余新能源充电；
- 储能不能从电网充电；
- 储能不能同小时充电和放电；
- 储能不能放电上网；
- 储能 SOC 必须逐小时滚动；
- SOC 不得低于 `soc_min`，不得高于 `soc_max`；
- 储能充放电受功率、容量、效率约束；
- 支持 8760 和 8784 小时数据；
- 光伏、风电负值按站用电口径处理；
- 输出必须保留方案汇总和可复核的逐小时明细。

未来如果允许柴油或电网给储能充电，必须做能源来源标记，不能把非新能源电量计入新能源自发自用。

## 建议目标架构

后续开发应逐步向以下对象和模块靠拢：

```text
ProjectStudy
InputDiagnostics
ScenarioPool
CandidateScenario
HourlyEnergyLedger
DispatchStrategy
PolicyEvaluation
EconomicEvaluation
ScenarioRecommendation
RecommendationPortfolio
StudyResult
ResultStore
```

推荐新增模块方向：

```text
domain/
engine/
services/
recommendation/
economy/
```

不要一次性大重构。优先小步迁移、保持测试通过、保持接口可追溯。

近期优先级应放在逐小时计算、风光储规模配置逻辑、轻量经济性排序、政策筛选和代表方案推荐上。图表和报告应等这些结果稳定后重新设计。

## 开发规则

- 每次只完成当前任务需要的最小稳定改动。
- 不要一次性重写整个项目。
- 不要删除测试。
- 不要删除文档。
- 修改算法前必须说明原因，并同步测试和文档。
- 如果发现需求矛盾，先记录并说明，不要静默猜测。
- 如果测试失败，应优先修复测试失败。
- 面向 Codex 或 Claude Code 的长期开发任务，应优先更新 `AGENTS.md` / `CLAUDE.md` / `notes/architecture_reframe_20260519/`。

## 完成标准

一个阶段完成必须满足：

1. 代码能运行，或文档逻辑自洽；
2. 相关测试通过；
3. 文档没有被破坏；
4. 没有无意引入未说明的调度口径变化；
5. 输出或接口变化有文档说明；
6. 说明修改了哪些文件。

## 长期记忆维护

不要假设历史聊天一定会保留。重要上下文必须沉淀到项目文件夹中。

当产品方向、计算口径、经济性、柴发、推荐逻辑、专家意见或用户体验判断发生变化时，更新 `notes/PRODUCT_POLISH_LOG.md`。

当换电脑继续开发所需的信息发生变化时，更新 `notes/HANDOFF_FOR_NEW_MACHINE.md`，包括必读文档、第一句提示词、下一步开发顺序和环境运行说明。
