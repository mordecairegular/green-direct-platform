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
经济性评价 V1 口径已于 2026-05-21 确认，并于 2026-05-22 更新储能更换与 FIRR 求解口径。请先阅读 docs/ECONOMY_RECOMMENDATION_V1_MAP.md、docs/references/economic_evaluation/00_README_使用说明.md 和 docs/references/economic_evaluation/经济性评价V1计算口径_合并版.md。V1 是不考虑贷款的年度项目投资现金流模型，Year 0 建设、默认运营期 25 年，运行成本无进项税，储能更换进项税保留；储能更换取循环寿命和默认 15 年日历寿命先到者，换后重新开始计算；FIRR 不使用折现率，且多次变号时应先判断是否只有唯一稳定 IRR 根；经济性评价不得修改技术调度结果。注意同一主体 `net_avoided_grid_cost_price` 与负荷侧 `load_side_avoided_charge_price` 是两个不同价格口径，不要混用。
```

如果本次任务会继续开发图表或推荐展示，还建议追加：

```text
图表模块已于 2026-05-21 开始重构为“方案图谱”：系统代表方案 + 用户加入方案 + 方案总览/能量流向/运行时序/经济性分析。请先阅读 notes/PRODUCT_POLISH_LOG.md 中“图表模块重构：对标参考图的第一版方案图谱”。当前图表只读取技术结果和经济性 V1，不得反向修改调度结果。碳排放和经济敏感性暂未确认口径，不要凭空生成。
```

如果本次任务涉及恢复旧文档或旧打包产物，请注意：2026-05-21 已做项目清理，清理前检查点为 `535ee78 Checkpoint before repository cleanup`。旧图表模块讨论稿、历史 `outputs/` 导出样例、`build/`、`dist/`、`release/` 等已从工作区移除；必要时从该提交恢复。

如果本次任务涉及追溯早期 AI 构建提示词、V0.1 验收记录或旧状态快照，请到 `archive/20260522_historical_build_materials/` 查看。该目录是历史归档，不是当前活跃开发入口。

### 2.1 内部试用上线前 Claude Code 提示词

如果目标是 10-20 人内部试用上线，请优先使用 `docs/CLAUDE_CODE_INTERNAL_PILOT_PROMPTS.md`。

该文档把 Claude Code 任务拆成四类可复制提示词：
- 上下文读取；
- 上线前 review/debug；
- Streamlit UI 提升；
- 后台账户、Job 和 `ResultStore` 架构设计。

不要把 review/debug 和 UI 提升合并到同一轮。前者用于清 P0/P1 风险，后者用于提升六步工作流体验；两者的判断标准不同，混在一起容易漏掉上线风险。

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
- `docs/ECONOMY_RECOMMENDATION_V1_MAP.md`
- `docs/WEB_APP_WORKFLOW_AND_UI_RESTRUCTURE.md`
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
- 六模块 Streamlit 工程工作台第一版（推荐与图表已拆页）；
- 经济性评价 V1、同一主体税前测算和推荐方案 V1；
- 下网电价曲线 V1，可选 CSV / Excel 上传，且只能使用当前会话明确上传的曲线；
- 图表模块、HTML 图表包和 Word 友好 PNG 图表包；
- 启动器、端口自检、本地单机结果快照恢复和会话隔离的后台 PNG 生成；
- pytest 测试基线。

最近一次上线前交接检查，已验证：

```text
python -m pytest -q
169 passed
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

运行 Streamlit 优先使用统一启动器：

```powershell
.\START_GREEN_DIRECT_APP.bat
```

或使用 PowerShell 启动脚本，它会先做导入自检，并默认从 8503 到 8515 选择空闲端口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_green_direct_app.ps1
```

如果只检查环境：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_green_direct_app.ps1 -CheckOnly
```

构建独立方案遍历试用程序：

```powershell
.\scripts\build_batch_trial_exe.ps1
```

构建后试用入口位于：

```text
dist\GreenDirectBatchTrial\GreenDirectBatchTrial.exe
```

该入口只包含方案遍历、方案概览 Excel 和逐小时方案详表 ZIP 导出，不包含完整 Streamlit、图表、经济性评价和推荐引擎。发给同事时复制整个 `dist\GreenDirectBatchTrial\` 文件夹。

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

截至 2026-06-12：

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
- 第一版推荐组合默认优先级已改为：同一主体 FIRR 最优、电源侧 FIRR 最优、负荷侧可成交收益最优、工程代表方案。工程代表方案从政策达标最小投资、高绿电占比、高自发自用、低弃电中选一个，默认低弃电；负荷侧席位需先满足电源侧最低可接受 FIRR 约束，再按负荷侧年度综合用能收益排序；
- 电源侧投资收益最佳方案默认以 FIRR 作为主排序指标：在政策达标候选集内，先筛 FIRR 可可靠计算，主排 FIRR 从高到低，辅助排序依次为静态回收期更短、动态回收期更短、FNPV 更高。已确认“自发自用电价”正式重命名为“绿电结算价”，计算字段统一使用 `green_power_settlement_price_with_vat`；当前代码中的 `self_use_price_with_vat` 只能作为迁移期旧字段。推荐 V1 应支持 8760 / 8784 逐小时绿电结算价、上网电价和电网购电价格曲线，后续再支持 15min；
- 经济性 V1 已补充独立的送出线路工程投资字段。该费用与其他固定资产投资都发生在 Year 0，但送出线路是绿电直连必需项，不能长期归入其他固定资产投资；第一版直接输入“送出线路工程投资总额（万元，含税）”。Year 0 全部初始投资中可抵扣增值税的部分统一按 10% 建设投资进项税率计；年度现金流中送出线路按 20 年直线折旧，并在经济性汇总中保留 `dedicated_connection_line_investment_with_vat`；
- 经济性 V1 折旧口径已澄清：Year 0 初始投资按 20 年、残值 0、直线法折旧；运营期发生的新增可折旧投资从次年到运营期最后一年线性折旧，残值 0。储能更换已按该口径新增 `bess_replacement_depreciation`；
- 当前不建议在方案遍历技术仿真中引入光伏逐年衰减；后续可在经济性 V2 或高级参数中增加年度电量衰减修正。若未来允许风电、光伏运营期不同，必须同步定义多年技术电量变化，不要只改现金流年限；
- 已新增底层输入原则：能在 CSV/Excel 中更清晰处理的数据准备、参数推导或清洗逻辑，不要强行塞入网页 UI；新增 UI 控件前要先判断是否更适合模板输入；
- 已新增推荐引擎 V1 计算口径草案：`docs/references/recommendation_engine/推荐引擎V1计算口径草案.md`。已确认价格曲线模板采用 CSV/Excel 上传，不做网页逐项录入；环境价值作为固定单价高级选项，默认 0，不做时间曲线；所有推荐席位默认只在政策达标候选集中排序；
- 2026-05-25 已补充并实现同一主体税前 FIRR 第一版：`docs/references/recommendation_engine/同一主体购电节费与税前FIRR口径.md`、`src/green_direct/economy/electricity_saving.py`、`src/green_direct/economy/single_entity_evaluator.py`、`tests/test_single_entity_economy.py`。同一主体合并口径不使用绿电结算价计算项目整体收益；默认按 `net_avoided_grid_cost_price` 计算自发自用购电节费，需要复核时可按电费清单组价：电能量/市场购电价格、上网环节线损费用、系统运行费用、输配电价、政府性基金及附加。V1 主排序采用税前 FIRR，不默认计算所得税。原电源侧 `evaluate_scenario_economy()` 未改，继续作为电源侧投资收益近似模型；
- 2026-05-25 已接入同一主体税前经济性 UI 试算和下载闭环：技术方案汇总 Excel 保持纯技术指标；电源侧经济性和同一主体税前经济性在经济性区域分别展示、分别下载汇总表，并支持所选方案 Year 0-Year N 年度现金流 Excel。经济性逐年明细是正式软件的可审计输出能力，不是临时复核包；后续其他经济性视角也应提供相应明细导出；
- 2026-05-25 已纠偏经济性参数分组：通用参数不得放进某一个推荐视角的高级参数区；储能更换投资比例、储能更换进项税率是通用经济参数，电池日历寿命放入储能参数区并说明当前只影响经济性更换、不参与小时调度；用户侧电费拆分字段必须尽量对应电费清单，避免使用“可节省/不可节省”等抽象命名；
- 2026-05-26 已增强同一主体年度现金流下载：工作簿包含 `方案说明`、`年度现金流`、`字段说明` 三张表。年度现金流表头带序号，字段说明表解释计算关系和口径差异；方案说明表展示风光储规模、主要政策指标、电量指标和同一主体关键经济性指标。后续电源侧、负荷侧年度详表也应沿用“方案上下文 + 编号表头 + 字段说明”的可复核结构；
- 2026-05-27 已再次纠偏经济性入口：固定价参数默认展示，不再通过“启用同一主体”开关才显示；价格曲线才是高级参数，后续用 CSV/Excel 上传。经济性参数区按 `基本参数`、`成本费用`、`收入和税金` 和 `电费构成参数` 分组；Year 0 建设投资、送出线路、其他固定资产和建设投资进项税率属于 `基本参数`，运营期运维和储能更换属于 `成本费用`，储能更换需说明按日历寿命和循环寿命先到者触发。`绿电结算价` UI 说明需强调其非用户到户电价，不含输配电价、政府基金及附加、系统运行费和容需量电费等；经济性测算按钮一次计算当前已实现的电源侧和同一主体视角；
- `其他经营收入` 属于 `收入和税金`，但一般项目没有，应放在高级折叠区默认隐藏，不占用主输入界面；
- 2026-05-27 已修正 `外部购电净成本单价` 组价公式：该参数不是原外部购网电全部电量类费用，而是 `原外部购网电电量类成本单价 - 绿电直连自发自用仍需缴纳费用单价`。若自发自用绿电仍缴输配电价和政府性基金及附加，这两项不能算作节省。1192 号文系统运行费暂按下网电量缴纳，自发自用绿电不作为“绿电仍缴系统运行费用”扣减；代码已新增 `green_direct_retained_*` 字段并在组价模式中扣减；
- 2026-05-27 已确认负荷侧默认席位改为 `负荷侧可成交收益最优`：新增基础参数 `电源侧最低可接受 FIRR`，默认 7%，字段建议 `min_power_side_acceptable_firr`。本席位先筛政策达标、负荷侧收益为正、电源侧 FIRR 可可靠计算且不低于最低可接受 FIRR，再按负荷侧年度综合用能收益排序。若用户清空最低 FIRR，则不对本席位排序并提示缺少可成交性约束。V1 暂不反算绿电结算价，只在用户给定价格条件下排序；
- 2026-05-27 已实现推荐方案 V1 试用并补齐四个默认席位：`同一主体 FIRR 最优`、`电源侧 FIRR 最优`、`负荷侧可成交收益最优` 和可切换的 `工程代表方案`。页面经济性区域下方新增 `推荐方案 V1（试用）`；完成经济性评价后应同时构造四个席位，同一方案命中多个席位时合并标签，不应静默漏掉同一主体或电源侧 FIRR 席位。合并标签时必须同时保留各席位贡献的关键指标，不能出现命中负荷侧席位但负荷侧收益字段缺失的推荐表。推荐组合 Excel 包含推荐组合、电源侧经济性汇总、同一主体经济性汇总和负荷侧可成交收益明细；
- 2026-05-28 已新增经济性评价与推荐 V1 导览文档 `docs/ECONOMY_RECOMMENDATION_V1_MAP.md`，用于给第一次接触项目的人说明参数、含义、代码入口、推荐席位和计算方式；
- 2026-06-04 已接入价格曲线 V1：`src/green_direct/economy/price_curves.py` 支持 CSV / Excel 读取、中文字段映射、8760 / 8784 校验、时间戳 / hour_index / 行序对齐和逐方案年度金额聚合；`run_economic_study()` 可选接收 `price_curve` 与 `hourly_details`，曲线模式只影响经济性和推荐排序，不改变技术调度。价格曲线 V1 只作为下网购电账单原始组分曲线，推荐模板为 `samples/price_curve_template_down_grid.csv`，文档副本为 `docs/templates/price_curves/price_curve_template_down_grid.csv`，字段包括 `timestamp`、`hour_index`、电度/市场购电价、线损费、系统运行费、输配电价、政府性基金及附加，以及当前不参与计算的 `month`、`peak_valley` 辅助列；绿电结算价、上网电价、度电环境价值、增值税率、负荷侧可减少费用和同一主体税前净节费不放入模板，继续由网页固定参数或内部公式得到。政府性基金及附加按不含税处理，其他下网电价组分按含税处理；计算方法审阅文档见 `docs/PRICE_CURVE_ECONOMY_CALCULATION_METHOD.md`。UI 口径：电价曲线在“方案仿真”页作为可选项目级输入上传，只有当前会话明确上传后才保存到 `project_price_curve_data` / `project_price_curve_meta` 并供“经济性测算”页使用；`.runtime/latest_session_snapshot.pkl` 不恢复旧价格曲线，用户只上传负荷、光伏、风电三条技术曲线时不得沿用历史电价。已有当前上传曲线时置灰外部购电净成本固定输入、电费清单组价开关和负荷侧单独覆盖。更换曲线或重跑技术仿真会清空旧经济性/推荐结果；测试见 `tests/test_price_curves.py`、`tests/test_study_runner.py` 和 `tests/test_ui_import.py`；
- 2026-05-28 已调整推荐默认口径：工程代表方案默认改为 `政策达标最小投资`；同一主体席位保留 FIRR 默认视角，并支持切换为 `同一主体动态回收期最短`；固定价模式默认减少用户输入，由外部购电净成本口径内部派生负荷侧筛选价，需要精确区分时再使用高级覆盖或电费清单组价；
- 2026-06-01 已在 Streamlit 继续落地工作流：`欢迎页`、`方案仿真`、`经济性测算`、`方案推荐及图表概览`、`图表下载和报告生成`。保留旧页面名到新页面名的兼容映射，避免旧会话状态导致页面进入异常；方案仿真页不再继续渲染经济性和图表；经济性测算页计算成功后保存 `recommendation_v1_inputs`；推荐图表页集中展示推荐组合和图表分析；下载报告页集中导出方案汇总、逐小时明细、图表 HTML ZIP、技术+经济汇总和简版 Markdown 报告；
- 2026-06-02 已把 Streamlit UI 深度改造成工程软件工作台第一版：左侧深蓝固定导航，顶部轻量项目状态条，主区按模块组织。方案仿真页把曲线数据、候选方案池、政策约束和专业参数放在主工作区；经济性测算页保留完整参数但分层收纳；推荐页先展示代表方案卡片和图表概览；所有下载按钮集中到“图表下载和报告生成”页。按钮跳转继续使用 `_workflow_page_target` pending 状态，仿真和经济计算完成后用 `st.rerun()` 刷新顶部状态条；推荐图表页已优先消费正式 `RecommendationPortfolio`，下载页图表 HTML ZIP 的多方案对比范围收窄为“推荐组合 + 当前报告方案”；Demo 候选范围为 27 个小方案，浏览器验证显示 15 个达标方案，未再出现 `workflow_page` widget key 报错；
- 2026-06-03 已把静态推荐样板页映射进一步接入正式 Streamlit 推荐图表页：`docs/ui/recommendation_dashboard_sample.html` 仍只作为视觉参考，mock 数据只允许留在 `docs/ui/`；正式推荐页卡片读取 `RecommendationPortfolio` 和技术/经济真实字段，新增排序标识、上网比例、无候选/待排序状态区分；顶部状态条从 `hourly_details.timestamp` 推导数据时间范围；推荐页底部新增下载报告入口和状态提示，默认报告方案优先取推荐组合有效 `scenario_id`，真实 CSV/Excel/HTML ZIP/Markdown 下载仍集中到“图表下载和报告生成”页；浏览器验证已走通欢迎页、Demo 仿真、经济性测算、推荐页、运行时序典型日和下载页；
- 2026-05-28 已新增第一层服务抽象 `src/green_direct/services/study_runner.py`：`run_economic_study()` 统一执行电源侧和同一主体经济性，`build_recommendation_study()` 统一构造推荐组合，`RecommendationInputSnapshot` 保存推荐所需的价格和门槛输入；
- 2026-06-04 已继续抽出技术研究服务入口：`TechnicalStudyInput`、`TechnicalStudyResult`、`StudyResult` 和 `run_technical_study()` 已落地；Streamlit 方案仿真页的 Demo 和正式测算不再直接调用 `read_curve_set()` / `run_batch()`，而是触发服务层。当前 UI 仍兼容写入 `batch_result`，同时新增 `study_result` 作为后续迁移入口；
- 2026-06-04 已把 Streamlit 主工作流调整为六模块：`欢迎页`、`方案仿真`、`经济性测算`、`方案推荐`、`图表概览`、`图表下载和报告生成`。旧 `方案推荐及图表概览` 会话状态映射到 `方案推荐`；02 页曲线卡 hover 显示负荷年总用电量、光伏/风电年利用小时；侧栏折叠态保留 48px 深蓝工具轨；Sankey 文字样式仅做展示层修正，不改变能源流向计算；
- 2026-06-01 已把四季典型日从固定月份中位日改为季节中心日法：按春 3-5 月、夏 6-8 月、秋 9-11 月、冬 12/1/2 月的完整 24 小时日期，使用负荷、风光、储能、电网、弃电、SOC 等逐小时字段标准化后选离季节平均曲线最近的真实日期；图表标题和说明标注 `MM/DD`；
- 2026-06-09 已在交付中心新增 Word 友好 PNG 图表包：HTML ZIP 继续用于 Plotly 交互复核，PNG ZIP 用于插入 docx。PNG 包复用同一图表清单并输出 `chart_manifest.csv`；默认 A4 纵向 Word 正文 16 cm 插入宽度、1800px 画布宽。静态 PNG 导出需要 `plotly>=6.1`、`kaleido>=1.0` 和可用 Chrome / Chromium；若环境缺失，HTML ZIP 不受影响，PNG 失败原因会写入 UI / warnings；
- 2026-06-09 已修复 Streamlit 启动入口与端口冲突问题：优先使用 `START_GREEN_DIRECT_APP.bat` 或 `scripts/start_green_direct_app.ps1` 启动；统一启动器会先做导入自检，默认从 8503 到 8515 选择空闲端口，并且只停止可确认属于本项目的旧 Streamlit 进程。不要再使用硬编码 8501 或裸 `streamlit run app.py` 的入口；若需要只检查环境，可运行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_green_direct_app.ps1 -CheckOnly`；
- 2026-06-10 已完成清理 C 盘后的 Streamlit 前端兼容排查：当前项目依赖应保持 `streamlit>=1.57,<1.58`、`plotly>=6.1`、`kaleido>=1.0`；启动器和 PyInstaller 入口会把 `TEMP/TMP/TMPDIR` 指向项目 `.runtime/tmp`，并自动设置 `BROWSER_PATH` 到本机 Chrome/Edge。若旧浏览器标签继续出现 `Failed to fetch dynamically imported module`，先强制刷新或重开 `http://localhost:8503`，因为正确的 `Metric`、`PlotlyChart`、`axios` 分块已验证可返回 JavaScript；PNG ZIP 已在当前 `.venv` 安装 `kaleido==1.3.0` 后验证可生成。
- 2026-06-10 已新增 Streamlit 重启后的本地结果恢复机制；2026-06-15 已按内部多人试用要求加安全边界：默认直接 `streamlit run src/green_direct/ui/app.py` 不保存、不恢复 `.runtime/latest_session_snapshot.pkl`，只有本地启动器 / PyInstaller 入口显式设置 `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=1` 时才启用。多人部署、内网服务器、容器或反向代理环境不得开启该变量；长期仍应实现正式 `ResultStore`；`.runtime/` 已加入 `.gitignore`。
- 2026-06-10 已修正图表网页端和 ZIP 导出一致性：新增共享能源色板 `src/green_direct/visualization/style.py`，网页 24H 运行策略图和 HTML/PNG 导出复用同一构图；PNG/HTML 图表包补充五类关键运行日和全年 8760/8784 曲线；季节典型日文件名不再嵌入日期，真实选中日期写入 meta。后续改图表颜色或 24H 运行图时优先改共享色板和 `build_operation_day_figure()`，不要单独给 PNG 另起一套样式。
- 2026-06-10 PNG ZIP 已改为后台生成；2026-06-15 已加多人试用安全修正：后台任务 key 包含 Streamlit 会话 ID，PNG ZIP 签名包含 `summary`、所选方案 `hourly_detail` 和对比方案表的数据指纹，新技术仿真会清空旧 PNG 导出缓存，快照也不再持久化 PNG ZIP 二进制。06 页提交后台线程任务，用户可切换页面，返回后自动收割结果；底层优先用 Plotly `write_images()` 批量渲染，失败再逐张回退。经济参数页默认风电造价 5000、光伏造价 2800，常调单位造价和运维单价使用 Streamlit 原生 `number_input` 内置步进微调，步长按字段内部定义（单位造价 100、运维 1），不要再用自定义按钮修改 `session_state` 后强制整页 rerun。顶部重复状态条已停止渲染，保留侧栏导航/状态和页面标题。PNG 图表包区域使用局部刷新显示运行中/完成/失败状态。S09 图中净交换显式按 `grid_export_power - grid_import_power` 展示，S10 全年曲线分为供需/上网弃电/SOC 三行，S02 政策阈值使用水平阈值线。
- 2026-06-15 已开始经济性测算性能优化：批量经济评价去除 `iterrows()`，年度折现因子按年限和折现率缓存，NPV 改用等价 Horner 形式，同一主体批量评价减少重复参数校验。该优化不改变年度现金流、FNPV、FIRR、回收期或推荐排序口径；后续仍需继续做 DataFrame/NumPy 批量化、后台 Job 和 `ResultStore`。
- 2026-06-15 已新增内部试用后台模型骨架：`src/green_direct/models/pilot_backend.py` 定义 `User`、`Project`、`ProjectMembership`、`ProjectStudy`、`Job`、`JobArtifact`、`StudyResultRecord`、`AuditLog` 及角色/任务/产物状态枚举。该骨架暂未接入登录页、数据库、任务队列或 Streamlit 管理页；下一步应基于它实现轻量 SQLite/Postgres 存储、管理员账户页和 `ResultStore`。
- 2026-06-15 已新增本地文件版 `LocalResultStore`：`src/green_direct/services/result_store.py` 可按项目/研究保存 `JobArtifact` payload、`StudyResultRecord` 和项目/全局 `AuditLog`，写入产物时自动记录 `storage_uri`、`sha256`、`size_bytes`，并校验路径片段防止路径穿越。该 store 暂未接管现有 Streamlit 工作流，后续应先让技术汇总、经济汇总、推荐组合和导出文件逐步写入 store。
- 2026-06-10 02 页“指定单方案”输入已做去冗和排版修正：模式入口保留“指定单方案”，但字段标签只写“光伏容量、风电容量、储能功率、储能容量”；四个输入采用两行两列，不再一行四列挤压中文标签。03 页经济性参数工作台也继续压紧：基本参数行改为四列节奏，Year 0 建设投资六个输入放到同一行，减少大块空白。后续新增参数控件时，优先让入口表达模式、字段表达名词，避免每个控件重复解释当前模式，也不要让少量字段横向撑满全屏。
- 2026-06-10 已进一步确认 UI 改造不能过度守旧：保留计算口径不等于保留旧页面结构。03 页经济参数已从单一“经济性参数工作台”大框拆为运行口径、建设投资、运维成本、收入和税金、到户电价展示、高级参数六个小工作卡；参数被放入 `st.form("economy_v1_params_form")`，顶部和底部都有“计算经济性 V1”提交按钮。表单内编辑常调参数时不再触发整页 rerun，浏览器测得风电单位造价输入改动前端响应约 82ms。后续 UI 工作应围绕“快速完成方案策划、经济测算、推荐和交付”主目标，不要为了沿用旧大表单而牺牲交互流畅性。
- 2026-05-25 已新增独立方案遍历试用程序入口：`src/green_direct/services/batch_trial_runner.py`、`src/green_direct/ui/batch_trial_gui.py`、`packaging/pyinstaller/run_batch_trial_tool.py`、`GreenDirectBatchTrial.spec` 和 `scripts/build_batch_trial_exe.ps1`。该入口只包装三条 CSV 读取、风光储容量枚举、逐小时技术仿真、方案概览 Excel 和全部方案逐小时详表 ZIP，不代表长期主产品要回到全量枚举表优先；配套说明见 `docs/BATCH_TRIAL_TOOL_USER_GUIDE.md` 和 `docs/BATCH_TRIAL_DISPATCH_AND_CALCULATION.md`；
- 下一步建议继续把推荐页、导出页和图表模块从兼容层 `batch_result` 逐步迁移到 `StudyResult` 读取；再补轻量 `ResultStore`，完善 `recommendation/` 模块的数据模型和导出契约，并为典型日选择、图表包和报告输出补充更细的审计数据。
