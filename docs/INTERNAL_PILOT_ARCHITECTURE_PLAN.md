# 内部试用上线架构计划

本文面向 10-20 人内部试用，不等同于正式公网 SaaS。目标是在不破坏 V0.1 风光储逐小时调度口径的前提下，把当前 Streamlit 单机工具逐步演进为可多人使用、可排队计算、可追踪项目结果的平台。

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
   - 支持管理员创建用户、停用用户、查看任务状态。

3. **Phase C：任务队列与持久化结果**
   - 技术仿真、经济性测算、PNG 导出都变为后台 `Job`；
   - 前台只提交任务、轮询状态、读取结果；
   - 计算进程可以横向扩展；
   - 下载文件从 `ResultStore` 或对象存储读取。

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
- `User.is_platform_admin` 已区分平台账号管理员和项目 `admin`，项目 `admin` 只管理项目成员，不能天然创建或停用全站账号；
- `Job` 已定义排队、运行、成功、失败、取消状态、进度字段及合法状态转换；
- `JobArtifact` 和 `StudyResultRecord` 保留 `project_id` / `study_id` 边界，用于后续 `ResultStore` 和下载文件隔离；
- 该骨架暂不包含登录页面、密码、数据库表、任务队列或 Streamlit 接入，不代表账户后台已经完整实现。

已落地的第一步 ResultStore：

- `src/green_direct/services/result_store.py` 提供 `LocalResultStore`；
- 产物按 `projects/{project_id}/studies/{study_id}/artifacts/{artifact_id}` 隔离保存；
- 写入产物时自动记录 `JobArtifact`、`storage_uri`、`sha256` 和 `size_bytes`；
- `StudyResultRecord` 可落盘并回读，用于把技术汇总、经济汇总、推荐组合、逐小时明细和报告产物串起来；
- 审计事件可按项目或全局写入 JSONL；
- 路径片段使用白名单校验，防止把用户输入直接拼成越权文件路径；
- 当前实现是本地文件适配器，不替代后续 SQLite/Postgres、对象存储或正式权限控制。

已落地的第一步账户/项目注册表：

- `src/green_direct/services/pilot_registry.py` 提供 `LocalPilotRegistry`；
- 支持保存、读取、列出和停用 `User`；
- 支持保存、读取、列出和归档 `Project`；
- 支持为项目授予/更新/停用用户角色，角色沿用 `admin`、`analyst`、`viewer`；
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
- 停用用户时会撤销该用户仍然有效的本地会话；
- 创建用户、更新用户、重置密码、停用和平台管理员标记变更会写入全局 `AuditLog`；
- 为避免锁死后台，服务不允许停用或降级最后一个活跃平台管理员；
- 当前服务仍未接入 Streamlit 管理员 UI，也未替代后续 SQLite/Postgres、企业身份系统或正式审计后台。

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
- `admin` 可创建/归档项目、授予/停用成员、提交任务、查看任务和产物、取消他人任务；
- `analyst` 可提交和查看本项目任务，并取消自己提交的任务；
- `viewer` 只能查看本项目任务和产物，不能提交或取消任务；
- 停用用户、停用 membership、非成员、已归档项目的新任务提交会被拒绝；
- 创建项目、成员变更、提交任务、取消任务、读取产物 payload 会写入 `AuditLog`；
- 当前服务仍不包含管理员 UI、worker 调度、数据库事务或并发锁；它只是后续 Streamlit 管理页和 SQLite/Postgres 适配器应复用的权限/审计语义。

试用版已有本地文件版密码与会话服务，可先用于开发和受控内网演示；正式内网版仍应评估 SQLite/Postgres 会话表、企业微信、OIDC、LDAP 或公司统一身份。

## 5. 性能优化路线

当前瓶颈来自两个方向：

- 方案遍历逐方案运行，成千上万方案时等待时间长；
- 每个成功方案都保存完整 8760/8784 小时明细，内存和 UI 压力大；
- 经济性测算对全部方案做年度现金流和 IRR，方案多时也会变慢。

已落地的第一步接口：

- `run_batch(..., retain_hourly_details=False, hourly_detail_scenario_ids=[...])` 可只返回方案汇总，或只保留指定方案逐小时明细；
- `PerformanceParams(parallel_workers=N)` 可让 `run_batch()` 使用 `ProcessPoolExecutor` 并行执行单方案技术仿真；默认 `1`，02 页“高级：枚举性能提醒”已暴露并行进程数；
- `TechnicalStudyInput(retain_hourly_details=False, hourly_detail_scenario_ids=(...))` 已把该能力接入服务层，并写入 `config_snapshot["detail_retention"]`；
- 02 页“高级：枚举性能提醒”已新增“大批量保留明细数”：当方案数超过提醒阈值时，UI 自动进入汇总优先模式，技术仿真只常驻方案汇总和前 N 个方案逐小时明细；
- 大批量汇总优先模式会清除当前项目级下网电价曲线，避免价格曲线经济性在缺少全量逐小时明细时误用部分数据；
- `run_economic_study(..., retain_annual_cashflows=False, annual_cashflow_scenario_ids=[...])` 可保留经济性 summary 指标，同时不常驻全部年度现金流表，或只保留报告方案/推荐组合现金流；
- 经济性批量评价已去除 `iterrows()` 行遍历，年度折现因子按年限和折现率缓存，NPV 使用等价 Horner 形式计算，同一主体批量评价只做一次公共参数校验；
- 这些接口和内部优化默认保持小规模旧行为，不改变 V0.1 技术计算口径或经济性口径。轻量保留接口主要降低大批量模式的内存、快照和结果传输压力；并行技术仿真和经济性底层优化为后续后台 Job 提供缩短等待时间的基础。

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
- P0/P1 风险清零或明确记录后，再做 UI 提升；
- UI 提升必须限制在当前 Streamlit 工程工作台内，不要改调度、经济性和推荐算法；
- 如果继续推进多人后台，单独使用账户、Job 和 `ResultStore` 架构提示词，不要和 UI 提升混在同一轮。
