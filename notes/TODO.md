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

专项文档：`docs/PERFORMANCE_OPTIMIZATION_PLAN.md`；可重复基准脚本：`scripts/benchmark_internal_pilot_performance.py`。

已完成：

- 单方案逐小时计算由 `iterrows()` 改为 NumPy 数组预分配。
- UI 筛选不再重复生成 Excel/ZIP。
- 汇总表默认限制显示行数。
- 技术批量入口已支持 `retain_hourly_details=False` 和指定方案明细保留，服务层 `TechnicalStudyInput` 已接入。
- 经济性入口已支持 `retain_annual_cashflows=False` 和指定方案年度现金流保留。
- 技术批量入口已支持 `PerformanceParams.parallel_workers`，02 页高级性能区已可配置并行进程数，默认 1。
- 并行技术仿真已改为按方案块提交给 `ProcessPoolExecutor`，减少大方案池下单方案 task 调度开销，结果顺序仍按原 `scenario_id` 聚合。
- 技术批量入口已支持 `PerformanceParams.max_scenarios_per_run`，容器和 UI 默认读取 `GREEN_DIRECT_MAX_SCENARIOS_PER_RUN=20000`；超限时 02 页会阻止开始测算，`run_batch()` 后端也会拒绝执行。
- 02 页已新增计算前工作量提示：按方案数、小时数、明细保留策略和并行进程数给出粗略耗时区间；超过方案数提醒阈值时需勾选大批量同步测算确认，才允许点击“开始测算”。
- 02 页已接入第一版大批量汇总优先模式：方案数超过提醒阈值时，只常驻方案汇总和前 N 个方案逐小时明细，N 由“大批量保留明细数”控制。
- 技术仿真已新增 summary-only 执行路径：未保留逐小时明细的方案仍逐小时滚动同一 dispatch/SOC 逻辑并累计 summary，但不构造完整 `hourly_detail` DataFrame。
- 服务层已新增 `run_hourly_detail_for_scenario()`，可在当前会话内基于技术 summary 行和原始 `TechnicalStudyInput` 为单个方案补算完整逐小时明细。
- Streamlit 推荐页、图表概览页和图表下载/报告页已接入第一版“补算逐小时明细”动作；补算后会写回当前 `batch_result` / `study_result` 并清除旧图表和下载缓存。
- 历史 summary-only 恢复后如果已有项目级 hourly artifact，图表/报告入口会优先按网页查看权限加载该明细；不可导出用户可网页查看但不能下载 artifact 文件。
- 历史 summary-only 恢复后如果没有 hourly artifact，但三条 input artifact 仍可查看且 `config_snapshot` 包含 `curve_columns`，图表/报告入口会恢复 `TechnicalStudyInput` 并跨会话补算单个方案明细；补算结果仍会写回项目级 hourly artifact。
- 大批量汇总优先模式会清除当前项目级下网电价曲线，避免缺少全量逐小时明细时误跑价格曲线经济性。
- Claude Code 上线前 review/debug、UI 提升和后台账户/Job/ResultStore 架构提示词已收敛到 `docs/CLAUDE_CODE_INTERNAL_PILOT_PROMPTS.md`。
- 经济性批量评价已做低风险底层提速：去除 `iterrows()`，缓存年度折现因子，NPV 使用等价 Horner 形式，同一主体批量评价减少重复参数校验；常规单符号变化现金流的 IRR 直接走二分快路径，多符号变化仍走原候选率扫描。
- 经济性 summary-only 已避免为未保留方案构造完整年度现金流 `DataFrame`；未保留方案仍用同一现金流数组计算 FNPV、FIRR 和回收期，只对报告/推荐/用户指定方案保留完整年度现金流表。
- 内部试用后台已新增持久化无关模型骨架：`User`、`Project`、`ProjectMembership`、`ProjectStudy`、`Job`、`JobArtifact`、`StudyResultRecord`、`AuditLog`。
- 服务层已新增 `LocalResultStore`，支持按项目/研究保存产物、结果索引和审计日志；当前已接入技术/经济/推荐 summary 写入、最小结果索引读取、结果索引软删除和结果标记/置顶，暂未接入数据库或完整历史结果恢复。
- 服务层已新增 `LocalPilotRegistry`，支持本地 JSON 用户、项目和项目成员角色管理，不包含密码或登录会话。
- 服务层已新增 `LocalPilotAuth`，支持本地密码哈希、登录会话、会话校验/撤销和登录审计；Streamlit 主 UI 已接入可选登录门禁和最小项目工作区门禁，但暂未接入正式身份系统。
- 服务层已新增 `LocalPilotAdminService`，区分平台管理员和项目管理员，支持首个管理员 bootstrap、创建用户、重置密码、授予/撤销平台管理员、停用用户并撤销会话，也支持平台管理员查看项目、授予/禁用项目成员；Streamlit 已接入最小平台管理页。
- `src/green_direct/cli.py` 已新增 `pilot-admin` 命令行入口，支持 bootstrap、创建用户、重置密码、停用用户、授予/撤销平台管理员、列出用户/会话/任务、清理过期 artifact payload 和标记超时 running 任务失败，作为管理员页面前的本地运维入口。
- Streamlit 主 UI 已新增可选内部试用登录门禁：设置 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1` 后，未登录用户不能进入六步工作流；登录使用 `GREEN_DIRECT_PILOT_STORE_DIR` 指向的本地账号 store，默认 `.runtime/pilot_store`。
- Streamlit 主 UI 已新增最小“平台管理”页：平台管理员可创建账号、重置密码、停用账号、授予/撤销平台管理员、查看会话，并在“项目和成员”中维护项目成员角色；普通用户看不到该入口。
- Streamlit 主 UI 已新增项目工作区门禁：启用 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1` 后，登录用户必须先创建或选择有效项目才能进入六步业务工作流；切换项目会清理当前测算结果和下载缓存。
- `ProjectMembership.can_export_artifacts` 已作为第一版独立导出授权位；平台管理页可维护“允许下载/导出项目结果”，历史 artifact payload 读取和 06 导出页会按该字段拦截；已落盘 artifact 下载和 06 页临时 CSV/Excel/ZIP/Markdown 下载都会写入 `DOWNLOAD_ARTIFACT` 审计。
- 上传入口已新增第一版文件门禁：技术曲线只允许 CSV，下网电价曲线允许 CSV/XLSX/XLSM，默认单文件上限 20MB，可通过 `GREEN_DIRECT_MAX_UPLOAD_MB` 调整；合法上传文件的文件名、后缀、大小和 SHA256 会写入技术仿真配置快照。启用内部试用登录并保存技术结果时，负荷/光伏/风电三条技术输入曲线会作为 `ArtifactKind.INPUT_CURVE` 保存，默认 30 天过期，并写 `STORE_ARTIFACT` 审计。
- Artifact 留存清理已新增第一版：`JobArtifact` 包含 `retention_policy`、`expires_at`、`purged_at`；`LocalResultStore.purge_expired_artifacts()` 会删除到期 payload 并保留元数据；`pilot-admin purge-expired-artifacts` 由平台管理员执行并写入 `DELETE_ARTIFACT` 审计。
- 内部试用部署材料已新增第一版：`.env.example`、`docs/INTERNAL_PILOT_DEPLOYMENT_RUNBOOK.md`、`scripts/backup_pilot_store.ps1` 和 `scripts/restore_pilot_store.ps1`，覆盖环境变量、账号 bootstrap、启动、备份、恢复、过期清理、冒烟检查和回滚边界。
- 受控公网内测审计矩阵已新增第一版：`docs/PUBLIC_BETA_DEPLOYMENT_AUDIT.md`，用于逐项跟踪 Route A 要求中已满足、部分满足和未满足的 P0 项。
- 性能基准脚本已新增第一版：`scripts/benchmark_internal_pilot_performance.py`，可对完整明细保留、summary-first 和经济性 summary-only 进行可重复耗时/内存记录。
- 服务层已新增 `LocalJobStore`，支持本地 JSON 任务提交、读取、全局/项目/研究列表、状态筛选、worker/heartbeat 元数据、进度更新、成功/失败/取消状态持久化，以及超时 running 任务扫描和置失败；暂未包含真正 worker 调度、重试、管理员页面或数据库锁。
- 服务层已新增 `PilotAccessService`，把项目角色权限、可见项目列表、任务提交/取消、产物读取和审计日志统一成可测试服务门面，暂未包含 worker 调度、数据库事务或并发锁。
- 本地 JSON store 共享写入 helper 已改为“写临时文件后原子替换”，降低账号、会话、任务、结果索引等 JSON 元数据半写损坏风险；这仍不等于数据库事务或跨进程并发锁。
- 技术仿真完成后已能在启用内部试用登录和当前项目时登记项目级同步 `Job`，并把 `technical_summary.csv`、`config_snapshot.json` 和 `StudyResultRecord` 写入 `LocalResultStore`；经济性 summary、已保留年度现金流、推荐席位输入、推荐 portfolio、按需补算的单方案逐小时明细、HTML 图表包和 Markdown 报告也已接入第一阶段项目级写入；PNG/Excel/批量包、完整报告和导出后台任务化仍待迁移。
- Streamlit 欢迎页已新增“项目任务与结果”面板，可查看当前项目任务数、已保存结果数、最近任务和最近结果索引；已落盘的技术 summary、经济 summary、年度现金流、推荐席位输入、推荐 portfolio/detail 等 artifact 可加载下载；技术 summary 已支持 summary-only 恢复到当前会话，并保留已有 hourly artifact 和 input artifact 索引用于后续图表/报告入口加载或补算；同一 `study_id` 的技术 summary 已恢复后，经济结果可恢复 summary、已保存年度现金流和推荐席位输入，推荐 portfolio 可 portfolio-only 恢复到当前会话；项目 admin 可标记/置顶历史结果索引，也可软删除/隐藏历史结果索引并写审计，但不物理删除 artifact。当前仍不恢复推荐视角选择或重新排序工作台状态，完整历史结果恢复和后台任务状态页仍待实现。
- Streamlit 欢迎页“项目任务与结果”面板已新增第一版“排队/运行中任务”区，可筛出当前项目活动任务，并按项目角色允许 analyst 取消自己任务、admin 取消项目任务；取消动作仍通过 `PilotAccessService.cancel_job()` 做后端权限校验和审计。该入口只是任务状态控制面板第一步，还不是真正 worker 级资源中断、重试或排队系统。

后续方向：

- 大批量模式继续补 worker 级后台进度/取消闭环、性能基准记录和完整任务状态页；当前前台预计耗时与大任务确认已是第一版粗略护栏，后续可用服务器实测数据校准。
- 把当前同步单方案逐小时明细补算继续升级为项目级后台任务；历史 summary-only 恢复后的 input artifact 补算已可用第一版，但还没有 worker 级进度、取消、重试和排队。
- 用户选择代表方案、图表方案或导出方案后，已有项目级 hourly artifact 已可优先加载；下一步是没有 artifact 时提交后台按需补算任务。
- 下一阶段把完整历史结果恢复、推荐视角选择与重新排序工作台状态、PNG/Excel/批量包、完整报告导出也提交为项目级后台 `Job`，并把对应 hourly/chart/report/export artifacts 写入 `ResultStore`；summary-only 经济运行如需后补年度现金流，应作为按需 Job 生成。
- 技术仿真已完成当前进程内 `ProcessPoolExecutor` 按方案块并行；下一步评估后台任务队列时继续沿用块级调度，保持 `scenario_id`、warning、error 和顺序稳定。
- 经济性测算继续做 DataFrame/NumPy 批量化和后台 Job 化；完整年度现金流已可先只对报告方案、推荐组合或用户指定方案生成。
- 本地 JSON 写入已做原子替换；下一步仍需补数据库/跨进程锁/并发冲突策略。
- 后续再评估 Numba、编译化调度内核或更高性能的数据结构。

### 2.1 内部 10-20 人试用上线架构

状态：已形成初步计划，详见 `docs/INTERNAL_PILOT_ARCHITECTURE_PLAN.md`。

近期方向：

- 多人部署默认关闭项目级运行快照，避免新会话恢复上一位用户结果；
- 后台 PNG 任务和下载缓存按 Streamlit 会话隔离；
- 先用受控内网/VPN/反向代理做内部试用；
- 如果开放公网访问，只按“受控公网内测 Route A”推进：关闭开放注册，用户由管理员创建或邀请，保留不接真实电力控制系统的边界说明；
- 继续收口导出授权：已完成 membership 级 `can_export_artifacts` 第一版，当前 06 页临时下载审计和 HTML 图表包 / Markdown 报告显式保存已走项目权限；下一步需要让未来 API、反向代理下载路径、对象存储签名 URL 和数据库适配全部复用同一后端策略；
- 继续补文件安全和留存策略：已完成上传类型/大小第一层门禁、hash 记录、技术三曲线 input artifact、基于 input artifact 的跨会话明细补算、artifact payload 到期清理、按需 hourly artifact、HTML 图表包和 Markdown 报告第一版；下一步让价格曲线、剩余现金流、PNG/Excel/批量包和完整报告存在仓库外受控目录，并补定时清理、关键 Run 保留和恢复策略；
- 继续补部署材料：已完成 `.env.example`、内部试用 runbook、pilot store 备份/恢复脚本、Dockerfile、docker-compose、`README_DEPLOY.md` 和 `SECURITY.md` 第一版；下一步在目标服务器实机演练 Docker build/up、HTTPS 反向代理、日志轮转、健康检查、监控告警和恢复演练；
- 下一阶段把 `pilot_backend` 模型、`LocalPilotRegistry`、`LocalPilotAuth`、`LocalPilotAdminService`、`LocalJobStore`、`LocalResultStore` 和 `PilotAccessService` 接入轻量 SQLite/Postgres、完整后台任务状态页和正式项目结果存储；
- 下一阶段把技术仿真、经济性测算和图表导出提交为项目级 `Job`，并把产物写入 `ResultStore`；
- 依据 `notes/PRELAUNCH_QUALITY_REVIEW_20260615.md` 推进内部 pilot 上线前闭环：后台任务 worker、结果存储接入、部署 runbook、数据库/备份策略；
- 管理员页、任务提交入口和未来 worker 不应直接绕过 `PilotAccessService` 调用底层 store；
- 后台任务接入时以 `LocalJobStore` 的 `Job` 状态契约为临时边界，沿用 `worker_id`、`last_heartbeat_at` 和 stale running cleanup 语义，再替换为 SQLite/Postgres 或正式队列实现；
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
