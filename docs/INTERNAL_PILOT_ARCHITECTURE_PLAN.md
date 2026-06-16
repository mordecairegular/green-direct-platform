# 内部试用上线架构计划

本文面向 10-20 人内部试用，并兼容后续“受控公网内测 Route A”的准备工作，不等同于正式公网 SaaS。目标是在不破坏 V0.1 风光储逐小时调度口径的前提下，把当前 Streamlit 单机工具逐步演进为可多人使用、可排队计算、可追踪项目结果的平台。

## 1. 内部试用边界

内部试用允许：

- 由少量内部用户上传项目曲线、运行方案池、查看推荐组合和导出报告；
- 先使用 Streamlit 前台，但必须避免跨用户共享运行态；
- 先以轻量账户和项目隔离为主，不要求一次性完成企业级 IAM；
- 对大批量方案先提供排队、进度、取消和结果缓存，不要求立即完成终极高性能引擎。

内部试用不应允许：

- 新用户自动看到上一位用户的测算结果；
- 全局 `.runtime/latest_session_snapshot.pkl` 在多人部署中恢复数据；
- 进程级后台任务缓存跨会话复用用户结果；
- 经济性 V1 被包装为最终投资决策模型。

如果从内网/VPN 试用升级为可公网访问的受控 Beta，应按 Route A 理解：

- 只允许邀请或管理员创建用户登录，不开放社会化自注册；
- 产品仍只是绿电直连 / 源网荷储前期方案测算和政策指标初判工具，不接 EMS、SCADA、调度自动化、真实电表或任何生产控制网络；
- 必须区分平台管理员、项目管理员、可计算不可导出用户、可计算可导出用户；当前 `ProjectMembership.can_export_artifacts` 已提供第一版“可导出/不可导出”后端授权位，但未来 API、反向代理下载和对象存储签名仍必须复用同一语义；
- 上传、计算、结果查看、产物下载、管理员跨项目查看都应经过后端权限校验并写入审计日志；
- 原始上传文件、逐小时明细和导出文件需要保留期限和清理机制，项目元数据、参数快照、结果摘要和审计日志应更长时间保留；当前只完成了本地 artifact payload 过期清理第一版，尚未覆盖原始上传文件和定时调度；
- 公网内测前必须补充 `.env.example`、部署 runbook、HTTPS/反向代理说明、数据卷、备份/恢复和回滚说明；当前已有内部试用部署 runbook、本地 store 备份/恢复脚本、Dockerfile、docker-compose、`README_DEPLOY.md` 和 `SECURITY.md` 第一版，仍需在目标服务器实机演练，并补系统服务托管、日志轮转、监控告警和安全扫描。

## 2. 当前上线安全修正

2026-06-15 起，运行快照改为显式开启：

- 默认直接 `streamlit run src/green_direct/ui/app.py` 时不保存、不恢复 `.runtime/latest_session_snapshot.pkl`；
- 本地 Windows 启动器会设置 `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=1`，保留单机重启恢复体验；
- 多人部署、内网服务器、容器和反向代理环境不得设置该环境变量为真值；
- 快照只保存计算结果与配置，不再保存 PNG ZIP 二进制缓存。

PNG 图表包后台任务也按会话隔离：

- 后台任务 key 包含 Streamlit 会话 ID；
- PNG ZIP 缓存签名包含 `summary`、所选方案 `hourly_detail` 和对比方案表的数据指纹；
- 新技术仿真完成后清空旧 PNG 导出缓存，避免同名方案和同时间范围复用旧图。

上传文件也已先加第一层门禁：

- `UploadPolicy` 对 Streamlit 上传文件做后缀和大小检查；
- 默认单文件上限 20MB，可用 `GREEN_DIRECT_MAX_UPLOAD_MB` 调整；
- 技术曲线只允许 CSV，下网电价曲线允许 CSV/XLSX/XLSM；
- 合法上传文件的文件名、后缀、大小和 SHA256 会写入技术仿真的 `config_snapshot["upload_file_metadata"]`；
- 非法文件只显示拒绝原因，不进入预览、曲线读取或价格曲线解析。

2026-06-15 起，Streamlit 主界面已新增可选内部试用登录门禁：

- 默认不启用，避免影响本地开发和桌面单机体验；
- 多人内部试用部署可设置 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1`；
- `GREEN_DIRECT_PILOT_STORE_DIR` 应指向 `pilot-admin --store-dir` 使用的同一受控目录，默认 `.runtime/pilot_store`；
- 未登录用户只能看到登录表单，不能进入方案仿真、经济性测算、推荐或导出页面；
- 会话校验复用 `LocalPilotAuth.require_session()`，退出登录或会话失效时清理当前 Streamlit 会话内的测算结果和下载缓存；
- 登录后必须先创建或选择一个有效项目工作区，六步业务工作流才会继续渲染；切换项目会清理当前测算结果和下载缓存；
- 平台管理员登录后可进入“平台管理”，完成创建账号、重置密码、停用账号、授予/撤销平台管理员、查看会话，并在“项目和成员”中把用户加入已有项目或禁用项目成员关系；
- 这只是 Phase A/B 之间的最小门禁、项目工作区和账号/成员管理页，还不是正式数据库会话、企业 IAM、后台任务队列或项目级结果持久化。

## 3. 内部试用部署形态

建议分三步走：

1. **Phase A：受控内网 Streamlit**
   - 部署在内网服务器或 VPN 后；
   - 反向代理层做基本访问控制；
   - `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0` 或不设置；
   - 每次测算结果仅存在当前会话内存，重要结果由用户主动下载。

2. **Phase B：后台账户与项目隔离**
   - 引入登录、用户、项目、项目成员和角色；
   - 每个项目有独立 `ProjectStudy` 和 `StudyResult`；
   - 结果写入 `ResultStore`，而不是依赖 Streamlit `session_state`；
   - 支持管理员创建用户、停用用户、维护项目成员、查看任务状态。

3. **Phase C：任务队列与持久化结果**
   - 技术仿真、经济性测算、PNG 导出都变为后台 `Job`；
   - 前台只提交任务、轮询状态、读取结果；
   - 计算进程可以横向扩展；
   - 下载文件从 `ResultStore` 或对象存储读取。

4. **Phase D：受控公网内测 Route A**
   - 默认启用登录、项目隔离、后端导出权限和审计；
   - 通过 HTTPS 反向代理访问，生产密钥只来自环境变量；
   - 数据库存储优先 SQLite/Postgres，文件产物存放在仓库外受控挂载目录；
   - 明确备份、恢复、清理、回滚和管理员排障流程；
   - 保留“不接真实电力控制系统”的产品边界说明。

第一版内部试用部署步骤见 `docs/INTERNAL_PILOT_DEPLOYMENT_RUNBOOK.md`。该 runbook 记录了环境变量、首个管理员 bootstrap、多人部署启动命令、pilot store 备份/恢复、过期 artifact 清理、冒烟检查和回滚边界。

## 4. 后台账户模型设想

推荐最小领域对象：

- `User`：账号、显示名、状态；
- `Role`：`admin`、`analyst`、`viewer`；
- `Project`：一个绿电直连或微电网项目；
- `ProjectMembership`：用户在项目中的角色；
- `ProjectStudy`：一次输入曲线、方案池、政策和经济参数快照；
- `Job`：技术仿真、经济测算、推荐组合、图表导出的后台任务；
- `StudyResult`：技术结果、经济结果、推荐结果和导出文件索引；
- `AuditLog`：登录、上传、运行、下载、删除等审计记录。

已落地的第一步模型骨架：

- `src/green_direct/models/pilot_backend.py` 定义了持久化无关的 `User`、`Project`、`ProjectMembership`、`ProjectStudy`、`Job`、`JobArtifact`、`StudyResultRecord` 和 `AuditLog`；
- `ProjectMembership` 已区分 `admin`、`analyst`、`viewer` 的查看、提交任务和项目管理权限；
- `ProjectMembership.can_export_artifacts` 已作为第一版独立导出授权位，可表达“可计算、可查看但不可导出”的内部试用成员；
- `User.is_platform_admin` 已区分平台账号管理员和项目 `admin`，项目 `admin` 只管理项目成员，不能天然创建或停用全站账号；
- `Job` 已定义排队、运行、成功、失败、取消状态、进度字段及合法状态转换；
- `JobArtifact` 和 `StudyResultRecord` 保留 `project_id` / `study_id` 边界，用于后续 `ResultStore` 和下载文件隔离；
- `JobArtifact` 已包含 `retention_policy`、`expires_at` 和 `purged_at`，用于表达 payload 长期保留或到期清理状态；
- 该骨架已被本地认证、最小 Streamlit 登录门禁和项目工作区复用，但仍不包含正式数据库表、任务队列或完整企业 IAM，不代表账户后台已经完整实现。

已落地的第一步 ResultStore：

- `src/green_direct/services/result_store.py` 提供 `LocalResultStore`；
- 产物按 `projects/{project_id}/studies/{study_id}/artifacts/{artifact_id}` 隔离保存；
- 写入产物时自动记录 `JobArtifact`、`storage_uri`、`sha256` 和 `size_bytes`；
- `StudyResultRecord` 可落盘并回读，用于把技术汇总、经济汇总、推荐组合、逐小时明细和报告产物串起来；
- `StudyResultRecord` 已支持按项目或研究列出，供项目内结果索引面板读取；
- `purge_expired_artifacts()` 可删除已过期 artifact payload，同时保留元数据和历史索引；
- 审计事件可按项目或全局写入 JSONL；
- 路径片段使用白名单校验，防止把用户输入直接拼成越权文件路径；
- 当前实现是本地文件适配器，不替代后续 SQLite/Postgres、对象存储或正式权限控制。

已落地的第一步账户/项目注册表：

- `src/green_direct/services/pilot_registry.py` 提供 `LocalPilotRegistry`；
- 支持保存、读取、列出和停用 `User`；
- 支持保存、读取、列出和归档 `Project`；
- 支持为项目授予/更新/停用用户角色，角色沿用 `admin`、`analyst`、`viewer`，并可独立维护是否允许下载/导出 artifact；
- 写入成员关系时会检查用户和项目已存在，避免孤立 membership；
- 当前注册表不存储密码、不处理登录会话、不替代正式认证；后续登录页或企业身份集成只应把认证主体映射到这些 `User` / `ProjectMembership` 记录。

已落地的第一步本地认证服务：

- `src/green_direct/services/pilot_auth.py` 提供 `LocalPilotAuth` 和 `PilotAuthError`；
- 密码哈希、salt、算法和迭代次数保存在 `auth/credentials/{user_id}.json`，不写入 `User` 模型，不保存明文密码；
- 登录成功后生成本地会话，`auth/sessions/{session_id}.json` 只保存 token 的 SHA256，不保存明文 bearer token；
- 支持设置密码、按 `login_name` 登录、校验会话、撤销会话和列出用户会话；
- 登录成功和失败可写入全局 `AuditLog`；
- 停用用户不能设置密码、登录或继续使用已有会话；
- 当前认证服务只适合受控内部试用，不替代企业 IAM、OIDC、LDAP、反向代理认证、CSRF 防护或正式数据库会话表。

已落地的第一步平台账号管理服务：

- `src/green_direct/services/pilot_admin.py` 提供 `LocalPilotAdminService` 和 `PilotAdminError`；
- 支持 bootstrap 首个 `is_platform_admin=True` 的平台管理员，并设置本地密码；
- 平台管理员可创建用户、设置初始密码、重置密码、授予/撤销平台管理员标记、停用用户和列出用户；
- 平台管理员可列出项目、查看项目成员、授予/更新项目角色、维护导出授权、禁用项目成员关系；
- 停用用户时会撤销该用户仍然有效的本地会话；
- 创建用户、更新用户、重置密码、停用和平台管理员标记变更会写入全局 `AuditLog`；
- 为避免锁死后台，服务不允许停用或降级最后一个活跃平台管理员；
- `src/green_direct/cli.py` 已提供 `pilot-admin` 命令行入口，可执行 bootstrap、创建用户、重置密码、停用用户、授予/撤销平台管理员、列出用户、列出会话和清理过期 artifact payload；
- 当前服务已接入 Streamlit 最小平台管理页，但仍未替代后续 SQLite/Postgres、企业身份系统或正式审计后台。

已落地的第一步 JobStore：

- `src/green_direct/services/job_store.py` 提供 `LocalJobStore`；
- 任务元数据按 `projects/{project_id}/studies/{study_id}/jobs/{job_id}.json` 隔离保存；
- 支持提交、读取、按项目/研究列出任务，并可按 `queued`、`running`、`succeeded`、`failed`、`canceled` 状态筛选；
- 支持 `start_job()`、`update_job_progress()`、`succeed_job()`、`fail_job()` 和 `cancel_job()`，状态合法性沿用 `Job` 模型；
- 路径片段使用白名单校验，防止 `project_id`、`study_id`、`job_id` 被拼接成越权路径；
- 当前实现只持久化任务状态，不包含 worker 调度、重试策略、并发锁、鉴权或管理员 UI；后续任务队列或数据库实现应沿用同一 `Job` 契约。

已落地的第一步权限与审计服务：

- `src/green_direct/services/pilot_access.py` 提供 `PilotAccessService` 和 `PilotAccessError`；
- 该服务组合 `LocalPilotRegistry`、`LocalJobStore` 和 `LocalResultStore`，让 UI、后台 worker 或未来管理页通过同一入口做项目访问控制；
- `list_accessible_projects()` 已用于 Streamlit 登录后的项目工作区选择，只返回当前用户有有效 membership 的项目；
- `admin` 可创建/归档项目、授予/停用成员、提交任务、查看任务和产物、取消他人任务；
- `analyst` 可提交和查看本项目任务，并取消自己提交的任务；
- `viewer` 只能查看本项目任务和产物，不能提交或取消任务；
- 成员是否能下载/导出 artifact 由 `can_export_artifacts` 独立控制，不再仅由 `viewer` / `analyst` / `admin` 推断；
- 结果索引读取已通过 `list_project_result_records()` / `list_study_result_records()` 纳入项目查看权限；
- 产物索引读取仍要求项目查看权限；网页内恢复/图表查看 payload 使用 `read_artifact_payload_for_view()`，要求项目查看权限并写入 `VIEW_ARTIFACT` 审计；文件下载/导出 payload 使用 `read_artifact_payload()`，要求项目导出权限，成功和拒绝都会写入 `DOWNLOAD_ARTIFACT` 审计；
- 停用用户、停用 membership、非成员、已归档项目的新任务提交会被拒绝；
- 创建项目、成员变更、提交任务、取消任务、读取产物 payload 会写入 `AuditLog`；
- 当前服务仍不包含 worker 调度、数据库事务或并发锁；它是当前 Streamlit 项目工作区、后续任务入口和 SQLite/Postgres 适配器应复用的权限/审计语义。

试用版已有本地文件版密码与会话服务，可先用于开发和受控内网演示；正式内网版仍应评估 SQLite/Postgres 会话表、企业微信、OIDC、LDAP 或公司统一身份。

## 5. 性能优化路线

详版路线、benchmark 命令和可复制给 Claude Code 的性能专项提示词见 `docs/PERFORMANCE_OPTIMIZATION_PLAN.md`。当前仓库已新增 `scripts/benchmark_internal_pilot_performance.py`，用于记录技术仿真完整明细保留、summary-first 和经济性 summary-only 的耗时与 Python 堆峰值。该脚本是优化决策辅助，不是固定性能门槛。

当前瓶颈来自两个方向：

- 方案遍历逐方案运行，成千上万方案时等待时间长；
- 每个成功方案都保存完整 8760/8784 小时明细，内存和 UI 压力大；
- 经济性测算对全部方案做年度现金流和 IRR，方案多时也会变慢。

已落地的第一步接口：

- `run_batch(..., retain_hourly_details=False, hourly_detail_scenario_ids=[...])` 可只返回方案汇总，或只保留指定方案逐小时明细；
- `run_single_scenario(..., retain_hourly_detail=False)` 已支持 summary-only 模式：仍按同一逐小时 dispatch 规则滚动 SOC 和累计技术指标，但不构造 8760/8784 行 `hourly_detail` DataFrame；
- `PerformanceParams(parallel_workers=N)` 可让 `run_batch()` 使用 `ProcessPoolExecutor` 并行执行单方案技术仿真；默认 `1`，02 页“高级：枚举性能提醒”已暴露并行进程数；
- `TechnicalStudyInput(retain_hourly_details=False, hourly_detail_scenario_ids=(...))` 已把该能力接入服务层，并写入 `config_snapshot["detail_retention"]`；
- `run_hourly_detail_for_scenario(inputs, scenario_id=..., summary=...)` 已提供当前会话内的单方案逐小时明细补算入口：从技术 summary 行重建 `Scenario`，复用同一次技术输入的原始曲线、BESS 参数、政策参数和 `dt_hours`，只补算选中方案；
- 02 页“高级：枚举性能提醒”已新增“大批量保留明细数”：当方案数超过提醒阈值时，UI 自动进入汇总优先模式，技术仿真只常驻方案汇总和前 N 个方案逐小时明细；
- 推荐页、图表概览页和导出/报告页已接入第一版“补算逐小时明细”按钮；缺少明细时会先尝试按网页查看权限加载已有 `ArtifactKind.HOURLY_DETAIL`，没有可用 artifact 再使用当前会话的原始技术输入补算；补算后写回当前 `batch_result.hourly_details` 和 `study_result.technical_result.batch_result`，并清空旧下载/图表缓存；在启用内部登录且当前技术结果已有项目索引时，会把补算出的单方案明细写为 `ArtifactKind.HOURLY_DETAIL` CSV，并挂回 `StudyResultRecord.hourly_detail_artifact_ids`；
- 大批量汇总优先模式会清除当前项目级下网电价曲线，避免价格曲线经济性在缺少全量逐小时明细时误用部分数据；
- `run_economic_study(..., retain_annual_cashflows=False, annual_cashflow_scenario_ids=[...])` 可保留经济性 summary 指标，同时不常驻全部年度现金流表，或只保留报告方案/推荐组合现金流；
- 经济性批量评价已去除 `iterrows()` 行遍历，年度折现因子按年限和折现率缓存，NPV 使用等价 Horner 形式计算，同一主体批量评价只做一次公共参数校验；常规单符号变化现金流的 IRR 使用二分快路径，多符号变化仍保留原候选率扫描和多根判断；
- 这些接口和内部优化默认保持小规模旧行为，不改变 V0.1 技术计算口径或经济性口径。summary-only 技术仿真让未保留明细的方案不再构造完整 hourly ledger，可同时降低大批量模式的耗时、内存、快照和结果传输压力；并行技术仿真和经济性底层优化为后续后台 Job 提供缩短等待时间的基础。

建议路线：

1. **计算前限流和预估**
   - 保留当前方案数预估；
   - 超过阈值时进入“大批量模式”，提示预计耗时和内存；
   - 支持取消任务和查看部分进度。

2. **汇总优先、明细按需**
   - 批量筛选阶段只保存 `summary` 和推荐所需最小明细；
   - 用户选中代表方案后，再生成该方案完整 `hourly_detail`；
   - 图表和报告只要求选中方案明细，不强制所有方案明细驻留内存。

3. **并行技术仿真**
   - 将单方案调度封装为可序列化任务；
   - 使用 `ProcessPoolExecutor` 或任务队列 worker 并行处理方案块；
   - 聚合时保持 `scenario_id`、warning、error 和顺序稳定；
   - 不改变现有储能调度口径。

4. **经济性批量向量化**
   - 对年度固定参数、投资、运维、替换、税费尽量用 DataFrame/NumPy 批量计算；
   - IRR/NPV 先保留精确口径，但按方案数组批处理；
   - 推荐 V1 先基于轻量经济 summary 排名，只有报告方案生成完整年度现金流表。

5. **结果缓存**
   - 对曲线文件、方案池、政策、储能和经济参数生成输入指纹；
   - 相同输入直接读取 `ResultStore`；
   - 用户改动任一关键输入时显式失效旧结果。

## 6. Claude Code 审查与 UI 提升提示词

完整可复制提示词已拆到 `docs/CLAUDE_CODE_INTERNAL_PILOT_PROMPTS.md`，避免本文件和换机交接文档维护两套长提示词。

使用建议：
- 先让 Claude Code 做上下文读取和上线前 review/debug；
- review 没有发现会阻断试用的计算口径或权限问题后，单独做一次性能专项，避免大方案池等待问题被 UI 打磨淹没；
- P0/P1 风险清零或明确记录后，再做 UI 提升；
- UI 提升必须限制在当前 Streamlit 工程工作台内，不要改调度、经济性和推荐算法；
- 如果继续推进多人后台，单独使用账户、Job 和 `ResultStore` 架构提示词，不要和 UI 提升混在同一轮。

## 2026-06-15 补充：技术仿真结果持久化第一阶段

已落地第一条项目级结果写入路径，并在随后补到经济 summary 和推荐 portfolio：
- `ArtifactKind.CONFIG_SNAPSHOT` 已加入后台模型；
- `PilotAccessService` 已支持 `start_job()`、`update_job_progress()`、`succeed_job()` 和 `fail_job()`，任务状态变更要求发起人本人或项目管理员权限，完成/失败写入 `AuditLog.COMPLETE_JOB`；
- `persist_technical_study_result()` 会把一次 `TechnicalStudyResult` 登记为 `technical_study` 类型同步 `Job`，写入 `technical_summary.csv`、`config_snapshot.json` 和 `StudyResultRecord(result_id="technical_result")`；
- Streamlit 02 页 Demo 和正式测算完成后，在启用内部登录且存在当前项目时，会调用该路径，并把结果引用挂到 `StudyResult.result_store_refs`。
- `persist_economic_study_result()` 会把一次 `EconomicStudyResult` 登记为 `economic_study` 类型同步 `Job`，写入电源侧和同一主体经济性 summary；
- `persist_recommendation_study_result()` 会把一次 `RecommendationStudyResult` 登记为 `recommendation` 类型同步 `Job`，写入推荐组合和负荷侧明细；Streamlit 推荐页使用 fingerprint 去重，避免同一组合刷新时重复写入。
- `LocalResultStore` 和 `PilotAccessService` 已支持按项目/研究列出结果索引；Streamlit 欢迎页已新增“项目任务与结果”面板，显示当前项目任务数、已保存结果数、最近任务和最近结果索引，并可加载下载已落盘的 summary / portfolio artifact；技术 summary 可 summary-only 恢复到当前会话，恢复时会带上已有 hourly artifact 索引。当前会话刚跑出的 summary-first 结果可按需补算单个方案明细，并把补算明细保存为默认 30 天过期的 hourly artifact；历史 summary-only 恢复如果已有 hourly artifact，可在图表/报告入口按网页查看权限加载；如果没有 hourly artifact 且没有原始输入 artifact，仍不能直接补算。

仍未落地：
- 后台 worker / 队列 / 取消闭环；
- 技术仿真历史 summary-only 结果基于受控原始曲线/输入 artifact 的跨会话补算；
- 经济性年度现金流、图表包、报告产物写入 `ResultStore`；
- 完整项目级任务状态页、完整历史结果恢复、删除、标记和跨项目搜索；
- SQLite/Postgres 或对象存储适配、并发锁、备份和部署 runbook。

下一阶段建议：
1. 先做完整任务状态页和结果历史恢复/下载页，让用户可以在项目内找回已完成测算；
2. 再把原始输入文件和经济性年度现金流纳入结果恢复链路，让缺少 hourly artifact 的历史结果也能受控补算；
3. 最后把图表包和报告导出统一变成项目级 artifacts，并接入后台 worker。
