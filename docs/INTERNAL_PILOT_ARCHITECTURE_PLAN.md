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

试用版可以先用 SQLite / Postgres 加密码登录；正式内网版再评估企业微信、OIDC、LDAP 或公司统一身份。

## 5. 性能优化路线

当前瓶颈来自两个方向：

- 方案遍历逐方案运行，成千上万方案时等待时间长；
- 每个成功方案都保存完整 8760/8784 小时明细，内存和 UI 压力大；
- 经济性测算对全部方案做年度现金流和 IRR，方案多时也会变慢。

已落地的第一步接口：

- `run_batch(..., retain_hourly_details=False, hourly_detail_scenario_ids=[...])` 可只返回方案汇总，或只保留指定方案逐小时明细；
- `PerformanceParams(parallel_workers=N)` 可让 `run_batch()` 使用 `ProcessPoolExecutor` 并行执行单方案技术仿真；默认 `1`，02 页“高级：枚举性能提醒”已暴露并行进程数；
- `TechnicalStudyInput(retain_hourly_details=False, hourly_detail_scenario_ids=(...))` 已把该能力接入服务层，并写入 `config_snapshot["detail_retention"]`；
- `run_economic_study(..., retain_annual_cashflows=False, annual_cashflow_scenario_ids=[...])` 可保留经济性 summary 指标，同时不常驻全部年度现金流表，或只保留报告方案/推荐组合现金流；
- 经济性批量评价已去除 `iterrows()` 行遍历，年度折现因子按年限和折现率缓存，NPV 使用等价 Horner 形式计算，同一主体批量评价只做一次公共参数校验；
- 这些接口和内部优化默认保持旧行为，不改变当前 UI、V0.1 技术计算口径或经济性口径。轻量保留接口主要降低大批量模式的内存、快照和结果传输压力；并行技术仿真和经济性底层优化为后续后台 Job 和 UI 大批量模式提供缩短等待时间的基础。

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
