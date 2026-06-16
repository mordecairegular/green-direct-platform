# Claude Code 内部试用上线提示词

本文用于把当前项目交给 Claude Code 做五类工作：

1. 内部 10-20 人试用上线前 review/debug；
2. 方案遍历与经济性测算性能专项；
3. 在不改变计算口径的前提下提升 Streamlit UI；
4. 后台账户、Job 和 `ResultStore` 架构设计；
5. 受控公网内测 Route A 的部署与安全缺口跟踪。

## 1. 对现有 GPT 提示词的判断

现有提示词方向是对的：应该把 Claude Code 分成“上线审查”“性能专项”“UI 提升”和“后台架构”几轮，而不是让它一次性同时做安全、性能、架构和视觉改造。

但原提示词还需要补强四点：

- 明确审查范围：要求 Claude Code 先确认当前分支、最近提交和工作区状态；
- 明确修复权限：P0/P1 可直接修，但任何计算口径变化必须先说明原因，并同步测试和文档；
- 明确 UI 边界：只优化当前 Streamlit 工程工作台，不重写为新前端，不把全量枚举表变成主入口；
- 明确交付证据：每轮都要给文件、行号、复现路径、验证命令和浏览器检查结果。

## 2. 使用顺序

建议按下面顺序给 Claude Code：

1. 先发送“上下文读取提示词”；
2. 再发送“上线前 review/debug 提示词”；
3. 如果 review 没有发现会阻断试用的计算口径或权限问题，再发送“性能专项提示词”；
4. 如果 P0/P1 清零或已有明确修复计划，再发送“UI 提升提示词”；
5. 如果要继续推进多人后台，再发送“后台账户、Job 和 ResultStore 架构提示词”。

不要把第 2 步、第 3 步和第 4 步合并。审查阶段要保守，性能阶段要可量化，UI 阶段要有设计判断，混在一起容易漏掉真正的上线风险或把视觉优化误当成上线能力。

## 3. 上下文读取提示词

```text
请先不要改代码。请阅读 AGENTS.md、CLAUDE.md、notes/HANDOFF_FOR_NEW_MACHINE.md、notes/PRODUCT_POLISH_LOG.md、docs/INTERNAL_PILOT_ARCHITECTURE_PLAN.md、docs/PUBLIC_BETA_DEPLOYMENT_AUDIT.md、docs/PERFORMANCE_OPTIMIZATION_PLAN.md、docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md、docs/ECONOMY_RECOMMENDATION_V1_MAP.md、docs/CHART_MODULE_CURRENT_LOGIC.md、docs/WEB_APP_WORKFLOW_AND_UI_RESTRUCTURE.md，以及 notes/architecture_reframe_20260519/ 下的文档。

读完后请用中文简要说明：
1. 当前项目定位；
2. V0.1 风光储技术仿真基线；
3. 内部 10-20 人试用上线边界，以及受控公网内测 Route A 与正式公网 SaaS 的区别；
4. 当前已做的多用户隔离和性能优化；
5. 后续开发时你会如何避免破坏计算口径。

然后执行：
git status --short --branch
git log --oneline -8
python -m pytest -q

请把当前分支和工作区视为既有工作，不要回滚用户或其他 agent 已经做出的改动。
```

## 4. 上线前 review/debug 提示词

```text
请按“内部 10-20 人试用上线前审查”全面 review/debug 当前项目。

审查范围：
1. 当前工作区；
2. 当前分支相对远端的新增提交，优先查看：
   git log --oneline origin/codex/UI..HEAD
   git diff --stat origin/codex/UI...HEAD
   如果没有 origin/codex/UI，请改用最近 5 个提交作为审查范围；
3. Streamlit 前台、服务层、批量技术仿真、经济性测算、推荐、图表/导出、启动器和测试。

重点审查：
1. 多人部署风险：
   - 是否存在跨用户 session_state 串数据；
   - 是否存在进程级全局缓存复用用户结果；
   - `.runtime/latest_session_snapshot.pkl` 是否会在多人环境默认恢复旧结果；
   - PNG/HTML/Excel/CSV/Markdown 下载是否可能拿到旧项目或其他用户的数据；
   - Web 平台管理页和 `pilot-admin` 项目生命周期/成员命令是否使用同一平台管理员权限语义；
   - 下网电价曲线是否只来自当前会话明确上传的数据。
2. 后台任务风险：
   - PNG ZIP 后台任务 key 是否按会话隔离；
   - 新技术仿真后旧导出缓存是否失效；
   - 欢迎页活动任务和任务状态明细是否只展示当前项目任务，取消入口是否仍走后端权限和审计；
   - `Job.worker_id` / `last_heartbeat_at`、`pilot-admin list-jobs` 和 `pilot-admin fail-stale-jobs` 是否能先查看超时 running 元数据、再转为 failed，并保留项目级审计；
   - `LocalJobStore.claim_next_queued_job()`、`PilotAccessService.claim_next_job_for_worker()` 和 `pilot-admin claim-next-job` 是否只认领 queued job、写入 worker/heartbeat、支持任务类型过滤，并跳过归档项目；命令是否明确不执行真实计算；
   - `pilot-admin list-audit-events` 是否只能由平台管理员读取，并能分别抽查全局审计和项目级审计；
   - 长任务失败、取消、重复点击、页面切换后的状态是否可恢复或可解释。
3. 计算口径风险：
   - V0.1 储能只能由富余新能源充电；
   - 储能不得从电网充电；
   - 储能不得放电上网；
   - 同小时不得同时充放电；
   - SOC 滚动、上下限、功率和容量约束不被破坏；
   - 支持 8760 和 8784 行；
   - 经济性、推荐、图表和报告只读取技术仿真结果，不反向改变调度。
4. 性能风险：
   - 成千上万方案时是否仍强制保留所有逐小时明细；
   - `retain_hourly_details`、`hourly_detail_scenario_ids`、`retain_annual_cashflows`、`parallel_workers`、`max_scenarios_per_run`、预计耗时提示和大批量确认的默认行为和 UI 接入是否一致；
   - 并行技术仿真是否保持 scenario_id、warning、error、进度和结果顺序稳定；
   - 经济性测算是否有继续批量化的明确下一步。
5. UI 和交付风险：
   - 六步工作流是否能从 Demo 跑通到推荐、图表和导出；
   - 错误提示是否能让内部试用用户知道下一步；
   - raw scenario enumeration 是否被放回主入口；
   - 图表模块是否被过度当成稳定架构锚点。
6. 受控公网内测 Route A 风险：
   - 是否关闭开放注册，或只允许管理员创建/邀请用户；
   - 是否明确不接 EMS、SCADA、调度自动化、真实电表或生产控制网络；
   - 项目角色是否被误当作完整公网内测角色体系，尤其是否缺少可导出/不可导出用户授权；
   - BETA_USER_NO_EXPORT 是否能通过直接 URL、缓存、artifact 读取或未来 API 绕过导出限制；
   - 上传文件是否限制类型、大小和 schema，文件路径是否按用户/项目/Run 隔离且不落入 Git 仓库；
   - 技术三曲线 input artifact 是否按项目/研究隔离保存、默认到期、只记录脱敏审计 metadata，并能在历史 summary-only 恢复时带回索引；
   - `JobArtifact.retention_policy` / `expires_at` / `purged_at` 和 `pilot-admin purge-expired-artifacts` 是否只删除到期 payload、保留元数据并写入审计；价格曲线、图表包、报告和关键 Run 是否仍缺留存策略；
   - 日志和错误提示是否可能包含原始曲线、明文 token、服务器绝对路径或敏感项目名；
   - 是否已有 `.env.example`、部署说明、HTTPS/反向代理、数据卷、备份、恢复和回滚说明。

输出要求：
1. 先列 Findings，按 P0/P1/P2 排序；
2. 每个 finding 必须包含文件路径、行号、复现方式、风险说明和建议修复；
3. P0/P1 如果不改变计算口径，可以直接修复；
4. 任何可能改变计算口径、经济性口径或推荐口径的修复，必须先说明原因，并同步测试和文档；
5. 最后列出已运行的验证命令、未能验证的风险和下一步建议。

完成后请运行：
python -m pytest -q

如果修改了前端，请用浏览器打开本地 Streamlit，至少检查 01 项目启动、02 方案仿真、03 经济测算、04 方案推荐、05 图表概览、06 下载报告没有明显异常。
```

## 5. UI 提升提示词

```text
请在不改变核心计算口径的前提下提升当前 Streamlit UI。

目标用户：
内部能源项目规划人员、技术经济测算人员和项目负责人。界面应像工程测算和规划辅助决策后台，而不是营销首页或展示型网站。

目标体验：
1. 01 项目启动：让用户快速知道输入是否齐备、结果是否可用、下一步该做什么；
2. 02 方案仿真：让曲线上传、方案池、政策约束、性能设置更清晰，避免把全量枚举表作为主入口；
3. 03 经济测算：提高参数分组和输入密度，减少大面积空白和反复 rerun；
4. 04 方案推荐：强化推荐席位、命中理由、风险提示和关键技术经济指标；
5. 05 图表概览：围绕代表方案和用户加入的对比方案组织图表，而不是围绕全部枚举结果；
6. 06 下载报告：清楚展示哪些文件已准备好、哪些需要先运行计算、导出失败如何处理。

允许做：
1. 调整文案、分组、折叠区、状态提示、按钮位置、信息密度和页面层级；
2. 增加必要的输入校验和用户友好错误提示；
3. 增加轻量 CSS 和 Streamlit 组件布局优化；
4. 为 UI 行为补充测试；
5. 删除明显重复或误导的界面文案，但不要删除功能入口。

不允许做：
1. 不要改 V0.1 技术调度口径；
2. 不要改经济性和推荐算法；
3. 不要把 Streamlit 重写为 React、Vue、FastAPI 或其他新架构；
4. 不要把 raw scenario enumeration 变成主页面核心体验；
5. 不要把图表模块当成不可替换架构锚点；
6. 不要为了视觉效果隐藏关键单位、计算口径和风险提示。

交付要求：
1. 每个 UI 改动都说明对应的用户任务；
2. 给出修改文件清单；
3. 运行 python -m pytest -q；
4. 用浏览器实际打开本地 Streamlit，检查六个页面；
5. 如果发现 UI 问题但本轮不修，请列为 P2/P3 后续项。
```

## 6. 性能专项提示词

```text
请做一次“方案遍历与经济性测算性能专项”，目标是支持内部 10-20 人试用中的大方案池测算。

边界：
1. 不改变 V0.1 技术调度口径；
2. 不改变经济性 V1 现金流口径；
3. 不改变推荐 V1 排序口径；
4. 不把性能优化做成一次性重写计算引擎。

请先阅读：
- docs/PERFORMANCE_OPTIMIZATION_PLAN.md
- src/green_direct/batch/batch_runner.py
- src/green_direct/core/single_scenario_simulator.py
- src/green_direct/services/study_runner.py
- src/green_direct/economy/economic_evaluator.py
- src/green_direct/economy/single_entity_evaluator.py
- tests/test_batch_runner.py
- tests/test_study_runner.py
- tests/test_economy_v1.py
- tests/test_single_entity_economy.py

先运行：
python scripts/benchmark_internal_pilot_performance.py --hours 168 --pv-count 4 --wind-count 4 --bess-power-count 2 --durations 0,2 --skip-full-retention --json
python -m pytest tests/test_batch_runner.py tests/test_study_runner.py tests/test_economy_v1.py tests/test_single_entity_economy.py -q

重点审查并优先处理：
1. 大方案池是否默认走 summary-first；
2. 按需逐小时明细是否与全量保留结果一致；
3. 并行仿真是否保持 scenario_id、warning、error、进度和结果顺序稳定；
4. 经济性测算是否仍为每个方案常驻年度现金流；
5. UI 的方案数硬上限、粗略耗时提示和大批量确认是否清晰，已有最小取消入口、`list-jobs` 和 stale running 置失败命令是否足够清晰，是否还需要后台 worker 的下一步切片；
6. benchmark 是否能复现优化前后差异。

允许直接修改不改变计算口径的性能与内存问题；任何可能改变技术 dispatch、经济性现金流或推荐排序的改动必须先说明，并同步测试和文档。

完成后请给出：
1. 优化前后 benchmark 命令和结果；
2. 修改文件清单；
3. 已运行测试；
4. 未解决瓶颈；
5. 下一步后台 Job / worker 建议。
```

## 7. 后台账户、Job 和 ResultStore 架构提示词

```text
请先做架构设计，不要一次性实现完整后台。

目标是支持内部 10-20 人试用，不是正式公网 SaaS。请先阅读 `src/green_direct/models/pilot_backend.py`、`src/green_direct/services/result_store.py`、`src/green_direct/services/pilot_registry.py`、`src/green_direct/services/pilot_auth.py`、`src/green_direct/services/pilot_admin.py`、`src/green_direct/services/job_store.py`、`src/green_direct/services/pilot_access.py` 和 `src/green_direct/cli.py`，把它们视为已经落地的第一步模型、本地文件版 ResultStore、本地账户/项目注册表、本地密码/会话认证服务、本地平台账号管理服务、本地任务状态存储、本地权限/审计服务和 `pilot-admin` 命令行运维入口，再基于当前 Streamlit 前台和 Python 服务层，设计下一阶段最小后台能力：
1. User、Role、Project、ProjectMembership；
2. ProjectStudy、StudyResult、ResultStore；
3. Job、JobStatus、JobArtifact，包含 queued job 认领、worker heartbeat、stale running cleanup 和未来真正 worker 的状态契约；
4. AuditLog，包括 `pilot-admin list-audit-events` 这类本地抽查入口与未来正式审计后台的边界；
5. 技术仿真、经济性测算、推荐组合、PNG/HTML/Excel/Markdown 导出的后台任务化；
6. 输入文件、结果文件和下载文件的隔离策略；
7. 可导出/不可导出用户的后端授权策略；
8. Artifact 留存策略、过期清理、关键 Run 保留和清理审计；
9. 与现有 `run_technical_study()`、`run_economic_study()`、`build_recommendation_study()` 的衔接方式。

请输出：
1. 最小数据模型；
2. 一期实现切片，要求每片都能独立测试和回滚；
3. 哪些部分可以继续留在 Streamlit，哪些必须抽到服务层；
4. 多用户部署时必须禁止或改造的现有机制；
5. 测试计划；
6. 迁移风险。

不要改变当前 V0.1 计算口径。不要为了后台架构一次性重写整个项目。
```
