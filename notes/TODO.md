# TODO.md

本文件记录后续模块、暂缓需求和规划项。  
`PRODUCT_POLISH_LOG.md` 负责记录“已经讨论过的产品打磨过程和决策原因”；本文件负责记录“未来要做什么”。

## 近期优先级

### 1. 图表制作模块

状态：待设计。

目标：

- 基于已上传的负荷、光伏、风电曲线和指定风光储方案，生成典型技术图表。
- 图表模块应相对独立，不与批量遍历模块强耦合。

初步入口：

- 用户输入负荷、光伏、风电曲线后，直接选择 1-5 个自定义风光储配置方案并制图。
- 用户完成批量遍历或经济性排序后，输入 1-5 个 `scenario_id`，对指定方案制图。

待明确：

- 具体图表类型；
- 图表字段口径；
- 单方案图表与多方案对比图表；
- 导出格式；
- UI 工作流；
- 是否与报告生成模块衔接。

### 2. 大批量方案性能优化

状态：内部试用上线前的核心工程路线，详见 `docs/INTERNAL_PILOT_ARCHITECTURE_PLAN.md`。

已完成：

- 单方案逐小时计算由 `iterrows()` 改为 NumPy 数组预分配。
- UI 筛选不再重复生成 Excel/ZIP。
- 汇总表默认限制显示行数。
- 技术批量入口已支持 `retain_hourly_details=False` 和指定方案明细保留，服务层 `TechnicalStudyInput` 已接入。
- 经济性入口已支持 `retain_annual_cashflows=False` 和指定方案年度现金流保留。
- 技术批量入口已支持 `PerformanceParams.parallel_workers`，02 页高级性能区已可配置并行进程数，默认 1。
- 02 页已接入第一版大批量汇总优先模式：方案数超过提醒阈值时，只常驻方案汇总和前 N 个方案逐小时明细，N 由“大批量保留明细数”控制。
- 大批量汇总优先模式会清除当前项目级下网电价曲线，避免缺少全量逐小时明细时误跑价格曲线经济性。
- Claude Code 上线前 review/debug、UI 提升和后台账户/Job/ResultStore 架构提示词已收敛到 `docs/CLAUDE_CODE_INTERNAL_PILOT_PROMPTS.md`。
- 经济性批量评价已做低风险底层提速：去除 `iterrows()`，缓存年度折现因子，NPV 使用等价 Horner 形式，同一主体批量评价减少重复参数校验。
- 内部试用后台已新增持久化无关模型骨架：`User`、`Project`、`ProjectMembership`、`ProjectStudy`、`Job`、`JobArtifact`、`StudyResultRecord`、`AuditLog`。
- 服务层已新增 `LocalResultStore`，支持按项目/研究保存产物、结果索引和审计日志，暂未接入 UI 或数据库。
- 服务层已新增 `LocalPilotRegistry`，支持本地 JSON 用户、项目和项目成员角色管理，不包含密码或登录会话。
- 服务层已新增 `LocalPilotAuth`，支持本地密码哈希、登录会话、会话校验/撤销和登录审计；Streamlit 主 UI 已接入可选登录门禁，但暂未接入管理员页面、项目权限拦截或正式身份系统。
- 服务层已新增 `LocalPilotAdminService`，区分平台管理员和项目管理员，支持首个管理员 bootstrap、创建用户、重置密码、授予/撤销平台管理员、停用用户并撤销会话，暂未接入 Streamlit 管理员页面。
- `src/green_direct/cli.py` 已新增 `pilot-admin` 命令行入口，支持 bootstrap、创建用户、重置密码、停用用户、授予/撤销平台管理员、列出用户和列出会话，作为管理员页面前的本地运维入口。
- Streamlit 主 UI 已新增可选内部试用登录门禁：设置 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1` 后，未登录用户不能进入六步工作流；登录使用 `GREEN_DIRECT_PILOT_STORE_DIR` 指向的本地账号 store，默认 `.runtime/pilot_store`。
- 服务层已新增 `LocalJobStore`，支持本地 JSON 任务提交、读取、项目/研究列表、状态筛选、进度更新、成功/失败/取消状态持久化，暂未包含 worker 调度、认证、管理员页面或数据库锁。
- 服务层已新增 `PilotAccessService`，把项目角色权限、任务提交/取消、产物读取和审计日志统一成可测试服务门面，暂未包含认证、管理员页面、worker 调度、数据库事务或并发锁。

后续方向：

- 大批量模式继续补前台预计耗时、后台进度、取消入口和任务状态页。
- 大批量模式下继续补代表方案按需逐小时明细计算，不再要求用户只能缩小范围或指定单方案复核。
- 用户选择代表方案、图表方案或导出方案后，再按需计算或加载该方案逐小时明细。
- 技术仿真优先评估 `ProcessPoolExecutor` / 后台任务队列，按方案块并行，保持 `scenario_id`、warning、error 和顺序稳定。
- 经济性测算优先做 DataFrame/NumPy 批量化，完整年度现金流可先只对报告方案或推荐组合生成。
- 后续再评估 Numba、编译化调度内核或更高性能的数据结构。

### 2.1 内部 10-20 人试用上线架构

状态：已形成初步计划，详见 `docs/INTERNAL_PILOT_ARCHITECTURE_PLAN.md`。

近期方向：

- 多人部署默认关闭项目级运行快照，避免新会话恢复上一位用户结果；
- 后台 PNG 任务和下载缓存按 Streamlit 会话隔离；
- 先用受控内网/VPN/反向代理做内部试用；
- 下一阶段把 `pilot_backend` 模型、`LocalPilotRegistry`、`LocalPilotAuth`、`LocalPilotAdminService`、`LocalJobStore`、`LocalResultStore` 和 `PilotAccessService` 接入轻量 SQLite/Postgres、管理员页面、项目列表/权限拦截和后台任务状态页；
- 下一阶段把 `pilot-admin` CLI 的账号管理能力接入 Streamlit 管理员页；
- 依据 `notes/PRELAUNCH_QUALITY_REVIEW_20260615.md` 推进内部 pilot 上线前闭环：管理员页、项目隔离、后台任务 worker、结果存储接入、部署 runbook；
- 管理员页、任务提交入口和未来 worker 不应直接绕过 `PilotAccessService` 调用底层 store；
- 后台任务接入时以 `LocalJobStore` 的 `Job` 状态契约为临时边界，再替换为 SQLite/Postgres 或正式队列实现；
- 技术仿真、经济性测算和图表导出逐步改为后台任务。

### 3. 离网型源网荷储模块

状态：待详细设计。

初步判断：

- 当前并网型模块可通过“上网比例 = 0%”近似做离网型方案初筛。
- 但真正离网型源网荷储需要单独定义供电可靠性、失负荷、电源备用、储能保供、弃电、柴油/备用电源等场景。

待明确：

- 是否允许下网；
- 是否允许失负荷；
- 是否设置可靠性指标；
- 是否配置备用电源；
- 储能保供策略；
- 离网场景下经济性评价口径。

### 4. 经济性评价模块

状态：待设计。

初步方向：

- 按建设项目经济评价方法设计。
- 支持同一主体和不同主体两类投资关系。
- 同一主体可先采用简化增量投资评价方法。
- 收入可包括：
  - 绿电直供电量节约的购电成本；
  - 新能源上网电费；
  - 其他用户输入收益项。
- 成本可包括：
  - 电源初始投资；
  - 线路投资；
  - 储能投资；
  - 运维费用；
  - 下网电费；
  - 输配电费、系统运行费、基金附加等。

待明确：

- IRR、NPV、投资回收期、LCOE 等指标优先级；
- 税费和折旧口径；
- 同主体与不同主体收益分配；
- 价格参数输入方式；
- 与批量方案排序的衔接方式。

### 5. 输出阅读体验优化

状态：待设计。

方向：

- Excel 字段中文化；
- 单位统一显示；
- 电量保留 0 位小数；
- 比例保留 2 位小数；
- 增加字段解释页；
- 可选生成更适合人工阅读的报告式 Excel。
