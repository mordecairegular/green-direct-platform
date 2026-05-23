# 换电脑与 AI 协作交接说明

日期：2026-05-22  
用途：在更换电脑、切换 Codex / Claude Code、丢失历史聊天或重新开始会话时，帮助 AI 无感接续本项目。

## 1. 核心原则

本项目应把重要上下文沉淀在项目文件夹内，而不是依赖某一次聊天记录。

原因：

- 项目文件夹在移动硬盘中，代码和文档可以方便切换电脑；
- Codex / Claude Code 的历史聊天不一定随项目文件夹迁移；
- 新电脑、新客户端或新会话可能完全不知道此前讨论；
- 因此，项目规则、产品决策、架构方向、计算口径和下一步计划必须写进仓库文档。

一句话：

```text
让项目文件夹自己成为长期记忆体。
```

## 2. 换电脑后第一句提示词

在新电脑、新会话、新 AI 工具中，建议第一句直接发送：

```text
请先不要改代码。请阅读 AGENTS.md、CLAUDE.md、notes/HANDOFF_FOR_NEW_MACHINE.md、notes/PRODUCT_POLISH_LOG.md、docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md，以及 notes/architecture_reframe_20260519/ 下的所有文档。读完后请用简短中文总结：当前项目定位、V0.1 基线、最新架构方向、下一步建议，并说明你后续开发时会如何维护 PRODUCT_POLISH_LOG.md 和 HANDOFF_FOR_NEW_MACHINE.md。之后再等我给具体任务。
```

如果本次任务会修改现有风光储核心计算逻辑，再追加：

```text
本次可能涉及核心计算，请额外阅读 ALGORITHM_SPEC.md、TEST_CASES.md、OUTPUT_SCHEMA.md，并在修改后运行 pytest。
```

如果本次任务会开发柴发、经济性或推荐引擎，再追加：

```text
本次可能涉及柴发、经济性排序或推荐引擎，请重点阅读 notes/architecture_reframe_20260519/04_HOURLY_DISPATCH_LOGIC_WITH_DIESEL.md 和 02_TARGET_ARCHITECTURE_AND_CALCULATION_LOGIC.md。不要把柴发混入电网下网，不要让经济性评价反向污染技术调度。
```

如果本次任务会开发经济性评价模块，还必须追加：

```text
经济性评价 V1 口径已于 2026-05-21 确认，并于 2026-05-22 更新储能更换与 FIRR 求解口径。请先阅读 docs/references/economic_evaluation/00_README_使用说明.md 和 docs/references/economic_evaluation/经济性评价V1计算口径_合并版.md。V1 是不考虑贷款的年度项目投资现金流模型，Year 0 建设、默认运营期 25 年，运行成本无进项税，储能更换进项税保留；储能更换取循环寿命和默认 15 年日历寿命先到者，换后重新开始计算；FIRR 不使用折现率，且多次变号时应先判断是否只有唯一稳定 IRR 根；经济性评价不得修改技术调度结果。
```

如果本次任务会继续开发图表或推荐展示，还建议追加：

```text
图表模块已于 2026-05-21 开始重构为“方案图谱”：系统代表方案 + 用户加入方案 + 方案总览/能量流向/运行时序/经济性分析。请先阅读 notes/PRODUCT_POLISH_LOG.md 中“图表模块重构：对标参考图的第一版方案图谱”。当前图表只读取技术结果和经济性 V1，不得反向修改调度结果。碳排放和经济敏感性暂未确认口径，不要凭空生成。
```

如果本次任务涉及恢复旧文档或旧打包产物，请注意：2026-05-21 已做项目清理，清理前检查点为 `535ee78 Checkpoint before repository cleanup`。旧图表模块讨论稿、历史 `outputs/` 导出样例、`build/`、`dist/`、`release/` 等已从工作区移除；必要时从该提交恢复。

如果本次任务涉及追溯早期 AI 构建提示词、V0.1 验收记录或旧状态快照，请到 `archive/20260522_historical_build_materials/` 查看。该目录是历史归档，不是当前活跃开发入口。

## 3. 当前项目定位

本项目已经从：

```text
绿电直连风光储多方案批量测算工具
```

升级规划为：

```text
绿电直连 / 微电网项目方案策划与推荐平台
```

旧 V0.1 风光储技术测算模块仍然是重要基线，但不再是最终产品边界。

新的目标流程：

```text
项目输入
-> 输入审查
-> 候选方案生成
-> 逐小时技术仿真
-> 政策合规筛选
-> 轻量经济性排序
-> 代表方案推荐
-> 图表、报告、导出
```

## 4. 当前重要文档

### 4.1 当前有效 AI 开发规则

- `AGENTS.md`
- `CLAUDE.md`
- `notes/HANDOFF_FOR_NEW_MACHINE.md`

### 4.2 架构重定向材料

- `notes/architecture_reframe_20260519/01_EXPERT_REVIEW_BRIEF.md`
- `notes/architecture_reframe_20260519/02_TARGET_ARCHITECTURE_AND_CALCULATION_LOGIC.md`
- `notes/architecture_reframe_20260519/03_MIGRATION_AND_POLISH_PLAN.md`
- `notes/architecture_reframe_20260519/04_HOURLY_DISPATCH_LOGIC_WITH_DIESEL.md`

### 4.3 当前接口和产品打磨记录

- `docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`
- `notes/PRODUCT_POLISH_LOG.md`

### 4.4 V0.1 技术基线

- `PRD.md`
- `ALGORITHM_SPEC.md`
- `DATA_SCHEMA.md`
- `OUTPUT_SCHEMA.md`
- `TEST_CASES.md`
- `UI_SPEC.md`
- `ECONOMY_EXTENSION_SPEC.md`

这些旧文档不删除，但应理解为 V0.1 基线，不是未来产品边界。

### 4.5 历史归档资料

- `archive/20260522_historical_build_materials/`

该目录保存早期 AI 构建提示词、历史验收记录、旧状态快照和已完成任务说明。后续开发默认不读取该目录，只有追溯历史时再看。

## 5. 当前代码基线

当前已有能力包括：

- CSV 数据读取和编码识别；
- 8760 / 8784 小时支持；
- 负荷、光伏、风电曲线校验；
- 光伏 / 风电负值按站用电处理；
- 风光储容量组合枚举；
- 单方案逐小时能量平衡；
- 储能 SOC 滚动；
- 储能功率、容量、效率约束；
- 上网比例政策约束；
- 与电网交换功率限制；
- 批量测算；
- 汇总 Excel 和逐小时 CSV / ZIP 导出；
- 基础 Streamlit UI；
- 图表模块初步实现；
- pytest 测试基线。

最近一次文档重定向后，已验证：

```text
python -m pytest
60 passed
```

## 6. 后续开发优先方向

建议顺序：

1. 结构化输入诊断；
2. `StudyResult` 和 `HourlyEnergyLedger` 骨架；
3. 推荐引擎和 `RecommendationPortfolio`；
4. 轻量经济性排序；
5. 柴发资产和离网 / 备用调度策略；
6. 大批量结果存储和按需明细；
7. UI 和报告围绕推荐方案重塑。

当前特别说明：

- 现有图表模块效果不理想，可以视为可替换原型，不需要优先保护；
- 后续不要把主要精力放在继续打磨现有图表模块；
- 应先把逐小时计算、风光储规模配置逻辑、轻量经济性排序、方案筛选与推荐逻辑搞清楚并实现；
- 等计算和推荐结果稳定后，再重新设计图表和报告展示。

不建议一开始就：

- 大规模重构所有目录；
- 直接重写核心算法；
- 直接做完整 NPV / IRR / 税费 / 融资模型；
- 草率加入柴发给储能充电；
- 把推荐逻辑写死在 Streamlit UI 中。

## 7. 每次开发后的文档维护规则

后续无论使用 Codex 还是 Claude Code，每次出现以下情况，都应更新文档。

### 7.1 必须更新 PRODUCT_POLISH_LOG.md 的情况

当发生以下任何一种情况：

- 用户提出新的产品判断；
- 用户否定或调整之前的方向；
- 形成新的计算口径；
- 形成新的 UI / 工作流判断；
- 形成新的经济性、柴发、推荐策略判断；
- 解决一个关键体验或计算问题；
- 专家提出被采纳或暂缓的建议。

更新方式：

```text
在 notes/PRODUCT_POLISH_LOG.md 末尾新增日期小节，
记录问题、讨论结论、状态、原因和经验。
```

### 7.2 必须更新 HANDOFF_FOR_NEW_MACHINE.md 的情况

当发生以下任何一种情况：

- 项目定位发生变化；
- 推荐的下一步开发顺序变化；
- 新增关键架构文档；
- 新增必须阅读的文档；
- 运行方式或测试命令变化；
- 重要模块落地，例如推荐引擎、柴发、经济性；
- 换电脑后第一句提示词需要调整。

更新方式：

```text
保持本文档简洁可读，
只记录换电脑和新 AI 会话继续开发所需的最新事实。
```

### 7.3 必须更新 AGENTS.md / CLAUDE.md 的情况

当发生以下任何一种情况：

- 对后续 AI 开发的规则发生变化；
- 允许或禁止某类改动；
- 核心架构方向变化；
- 必读文档列表变化；
- 新增必须遵守的算法边界。

### 7.4 必须更新架构文档的情况

当发生以下任何一种情况：

- 柴发调度策略确定；
- 储能是否允许柴发 / 电网充电确定；
- 经济性排序字段确定；
- 推荐方案类别确定；
- `HourlyEnergyLedger` 字段确定；
- `StudyResult`、`RecommendationPortfolio` 等对象实现或调整。

对应目录：

```text
notes/architecture_reframe_20260519/
```

## 8. 换电脑后环境检查

进入项目目录后建议先执行：

```powershell
git status --short
python -m pytest
```

如果依赖缺失：

```powershell
python -m pip install -r requirements.txt
```

运行 Streamlit：

```powershell
python -m streamlit run src/green_direct/ui/app.py
```

如果旧电脑或新电脑端口占用，换端口运行也可以：

```powershell
python -m streamlit run src/green_direct/ui/app.py --server.port=8503
```

## 9. Git 建议

虽然项目在移动硬盘上可以直接切换电脑，但仍建议使用 git 记录关键状态。

每次完成一轮重要文档或代码改动后：

```powershell
git status --short
git add AGENTS.md CLAUDE.md README.md ROADMAP.md notes docs archive src tests
git commit -m "Update planning and architecture handoff docs"
```

如果不想马上提交，至少在切换电脑前查看：

```powershell
git status --short
```

确认哪些文件是未提交改动，避免换电脑后忘记当前状态。

## 10. 新 AI 会话的工作要求

新的 Codex / Claude Code 会话应遵守：

- 开始前先读本文档和 `AGENTS.md` / `CLAUDE.md`；
- 不要假设自己记得历史聊天；
- 不要把旧 V0.1 文档当成未来边界；
- 不要删除旧测试和旧文档；
- 不要把经济性评价混入技术调度；
- 不要把柴发输出混入电网下网；
- 推荐方案应有解释理由；
- UI 主界面不要默认展示全量枚举表、逐小时大表或经济性年度明细大表；这些应作为高级展开或下载项；
- 图表后续应围绕推荐方案和用户加入对比方案，而不是围绕全量枚举结果；
- 每次形成重要产品判断后更新 `PRODUCT_POLISH_LOG.md`；
- 每次影响跨电脑接续的信息后更新本文档。

## 11. 当前交接摘要

截至 2026-05-22：

- 已完成 V0.1 风光储技术测算基线；
- 已形成图表模块初步能力；
- 已分析对标软件，并确认目标是方案策划与推荐平台；
- 已同意经济性排序应提前进入推荐逻辑；
- 已确认经济性评价 V1 口径：不考虑贷款，Year 0 建设，默认运营期 25 年，输出年度现金流详表、FNPV、FIRR、静态回收期和动态回收期；2026-05-22 已更新为储能更换取循环寿命和默认 15 年日历寿命先到者，换后重新开始计算；
- 已实现经济性评价 V1 初版：`EconomicParams`、年度现金流计算、批量经济性汇总、轻量 Streamlit 试用入口和 11 个经济性测试；
- 已确认候选方案池必须有绿电来源：批量生成层跳过 `pv_capacity <= 0` 且 `wind_capacity <= 0` 的组合，不再枚举无新能源无储能或仅储能方案；
- 已根据浏览器批注做一轮低风险 UI 收纳：隐藏大表和明细、统一中文字段名、只保留 CSV/Excel 下载入口；
- 已将 `docs/references/economic_evaluation/` 精简为 README、V1 合并口径和官方来源清单三类文件；
- 已同意柴发应进入方案逻辑，尤其用于离网和备用场景；
- 已明确现有图表模块效果不理想，可在后续重构中替换或丢弃，不作为近期重点；
- 已更新 `AGENTS.md` 和 `CLAUDE.md`；
- 已新增架构重定向专家审查材料；
- 已新增每小时风光储网柴调度核心逻辑草案；
- 已将早期 AI 构建提示词、V0.1 验收记录和旧状态快照降级归档到 `archive/20260522_historical_build_materials/`，当前活跃开发不再把这些资料作为入口；
- 推荐引擎讨论已确认：默认推荐组合不要求用户先选择投资主体结构，应同时展示多视角方案；当前经济性 V1 更接近不同主体下的电源侧投资收益模型；同一主体全局增量收益和负荷侧收益先预留，后续补口径；
- 第一版推荐组合默认优先级已改为：同一主体 FIRR 最优、电源侧 FIRR 最优、负荷侧 FIRR 最优、工程代表方案。工程代表方案从政策达标最小投资、高绿电占比、高自发自用、低弃电中选一个，默认低弃电；同一主体和负荷侧第一版可先预留接口，但不能遗忘；
- 电源侧投资收益最佳方案默认以 FIRR 作为主排序指标：先筛政策达标且 FIRR 可可靠计算，主排 FIRR 从高到低，辅助排序依次为静态回收期更短、动态回收期更短、FNPV 更高。当前经济性 V1 使用全年平均上网和自发自用电价，后续需预留 8760 逐小时价格；负荷侧购电价格第一版可固定，后续预留 8760 或 15min 价格曲线；
- 经济性 V1 已补充独立的送出线路工程投资字段。该费用与其他固定资产投资都发生在 Year 0，但送出线路是绿电直连必需项，不能长期归入其他固定资产投资；第一版直接输入“送出线路工程投资总额（万元，含税）”。Year 0 全部初始投资中可抵扣增值税的部分统一按 10% 建设投资进项税率计；年度现金流中送出线路按 20 年直线折旧，并在经济性汇总中保留 `dedicated_connection_line_investment_with_vat`；
- 经济性 V1 折旧口径已澄清：Year 0 初始投资按 20 年、残值 0、直线法折旧；运营期发生的新增可折旧投资从次年到运营期最后一年线性折旧，残值 0。储能更换已按该口径新增 `bess_replacement_depreciation`；
- 当前不建议在方案遍历技术仿真中引入光伏逐年衰减；后续可在经济性 V2 或高级参数中增加年度电量衰减修正。若未来允许风电、光伏运营期不同，必须同步定义多年技术电量变化，不要只改现金流年限；
- 已新增底层输入原则：能在 CSV/Excel 中更清晰处理的数据准备、参数推导或清洗逻辑，不要强行塞入网页 UI；新增 UI 控件前要先判断是否更适合模板输入；
- 下一步建议继续围绕推荐引擎排序口径完成设计，再实现独立 `recommendation/` 模块，把当前 `visualization/chart_ui.py` 中临时代表方案选择逻辑迁出 UI。
