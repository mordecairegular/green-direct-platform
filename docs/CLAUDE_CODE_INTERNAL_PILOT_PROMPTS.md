# Claude Code 内部试用上线提示词

本文用于把当前项目交给 Claude Code 做六类工作：

1. 内部 10-20 人试用上线前 review/debug；
2. 方案遍历与经济性测算性能专项；
3. 在不改变计算口径的前提下提升 Streamlit UI；
4. 后台账户、Job 和 `ResultStore` 架构设计；
5. 受控公网内测 Route A 的部署与安全缺口跟踪；
6. 托管平台公网测试演练。

## 1. 对现有 GPT 提示词的判断

现有提示词方向是对的：应该把 Claude Code 分成“上线审查”“性能专项”“UI 提升”“后台架构”和“托管部署演练”等几轮，而不是让它一次性同时做安全、性能、架构、部署和视觉改造。

但原提示词还需要补强五点：

- 明确审查范围：要求 Claude Code 先确认当前分支、最近提交和工作区状态；
- 明确修复权限：P0/P1 可直接修，但任何计算口径变化必须先说明原因，并同步测试和文档；
- 明确 UI 边界：只优化当前 Streamlit 工程工作台，不重写为新前端，不把全量枚举表变成主入口；
- 明确部署路线：当前短期公网测试优先用容器/PaaS 托管应用本体、Cloudflare 做 DNS/HTTPS/Access，不要盲目改成 Vercel 或 Cloudflare Pages/Workers 原生应用；
- 明确交付证据：每轮都要给文件、行号、复现路径、验证命令和浏览器检查结果。

## 2. 使用顺序

建议按下面顺序给 Claude Code：

1. 先发送“上下文读取提示词”；
2. 再发送“上线前 review/debug 提示词”；
3. 如果 review 没有发现会阻断试用的计算口径或权限问题，再发送“性能专项提示词”；
4. 如果 P0/P1 清零或已有明确修复计划，再发送“UI 提升提示词”；UI 提升建议先用“审查与切片选择”提示词，再用“小切片落地”提示词；
5. 如果要继续推进多人后台，再发送“后台账户、Job 和 ResultStore 架构提示词”；
6. 如果要直接公网试用，再单独发送“托管平台部署演练提示词”。

不要把第 2 步、第 3 步和第 4 步合并。审查阶段要保守，性能阶段要可量化，UI 阶段要有设计判断，混在一起容易漏掉真正的上线风险或把视觉优化误当成上线能力。

如果目标是“让 Claude Code 对 UI 进行提升”，不要直接发送一句“请美化界面”。应先让它用截图和浏览器证据审查当前 01-06 页，再选择一个可验收小切片落地。首次 UI 提升优先考虑“窄屏/手机宽度可用性”和“经济性/推荐/导出页的任务状态反馈”，因为它们直接影响同事在移动网络下试用时是否能完成闭环。

## 2.1 当前 checkpoint 交接摘要

截至 2026-06-17，本地 `codex/UI` 分支的最近 checkpoint 为：

- 最新提交主题：`perf(economy): trim summary hot path`
- `9de4638 perf(batch): stream scenario generation`
- `a5a75fd chore(perf): make parallel worker default configurable`
- `807fb1b chore(deploy): require private github source`
- `428fcfa chore(deploy): align browser path defaults`
- `86b9319 chore(deploy): check runtime dependency sync`

本地已验证：

```powershell
python -m pytest tests\test_batch_runner.py -q
python -m pytest tests\test_study_runner.py tests\test_ui_import.py::test_technical_workload_estimate_scales_with_detail_retention_and_workers tests\test_ui_import.py::test_scenario_count_limit_notice_blocks_oversized_pool -q
python -m compileall -q src\green_direct\batch\scenario_generator.py src\green_direct\batch\batch_runner.py scripts\benchmark_internal_pilot_performance.py tests\test_batch_runner.py
python scripts\preflight_internal_pilot_deploy.py --json
python scripts\preflight_internal_pilot_deploy.py --require-git-sync --json
```

当前已知状态：

- `python -m pytest -q` 最近一次全量记录为 `400 passed`；
- `tests\test_batch_runner.py` 最近一次专项结果为 `18 passed`；
- study runner + UI 性能提示相关专项最近一次结果为 `14 passed`；
- 部署静态 preflight 通过，已覆盖 Docker/Compose/Render 关键默认值、Web/worker 环境变量、`.dockerignore`、Git tracked 推送源安全和大文件检查；
- `preflight_internal_pilot_deploy.py` 支持 `--summary`，用于人类快速查看发布就绪总览、失败项和下一步建议；CI/agent 读取仍使用 `--json`；
- `--require-git-sync` 当前只应在本地分支尚未推送时失败 `git:sync`，最近状态为本地 `codex/UI` ahead `origin/codex/UI` 136、behind 0、工作树干净；推送前不要把这个失败误判为配置错误；
- 本项目已经具备 Render Blueprint / Docker / persistent disk / Cloudflare Access 的首发路线材料，但尚未完成目标托管平台实机部署演练；
- 不要为了接入 Vercel 或 Cloudflare Pages/Workers 直接把当前 Streamlit 长进程改成 serverless/edge 应用。短期公网内测优先保持 Docker Web Service 路线。
- `run_batch()` 已通过 `iter_scenarios()` 流式消费方案池，串行和并行 chunk 都不再先物化完整 `Scenario` list；这只是方案池对象生成和调度层优化，不改变 V0.1 技术调度、经济性或推荐口径。

如果 Claude Code 接手时当前分支仍领先 upstream，先报告：

```powershell
git status --short --branch
git log --oneline -8
python scripts\preflight_internal_pilot_deploy.py --require-git-sync --json
```

除非用户明确授权，不要擅自 `git push`、创建公网服务或修改托管平台配置。

## 3. 上下文读取提示词

```text
请先不要改代码。请阅读 AGENTS.md、CLAUDE.md、notes/HANDOFF_FOR_NEW_MACHINE.md、notes/PRODUCT_POLISH_LOG.md、docs/INTERNAL_PILOT_ARCHITECTURE_PLAN.md、docs/PUBLIC_BETA_DEPLOYMENT_AUDIT.md、docs/MANAGED_PUBLIC_BETA_DEPLOYMENT.md、docs/PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md、docs/MOBILE_NETWORK_TRIAL_CHECKLIST.md、docs/PERFORMANCE_OPTIMIZATION_PLAN.md、docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md、docs/ECONOMY_RECOMMENDATION_V1_MAP.md、docs/CHART_MODULE_CURRENT_LOGIC.md、docs/WEB_APP_WORKFLOW_AND_UI_RESTRUCTURE.md，以及 notes/architecture_reframe_20260519/ 下的文档。

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
python scripts\preflight_internal_pilot_deploy.py --json
python scripts\preflight_internal_pilot_deploy.py --summary

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
   - Web 平台管理页和 `pilot-admin` 项目生命周期/成员/审计命令是否使用同一平台管理员权限语义；
   - 下网电价曲线是否只来自当前会话明确上传的数据。
2. 后台任务风险：
   - PNG ZIP 后台任务 key 是否按会话隔离；
   - 新技术仿真后旧导出缓存是否失效；
   - 欢迎页活动任务和任务状态明细是否只展示当前项目任务，取消入口是否仍走后端权限和审计；
   - `Job.worker_id` / `last_heartbeat_at`、`pilot-admin list-jobs` 和 `pilot-admin fail-stale-jobs` 是否能先查看超时 running 元数据、再转为 failed，并保留项目级审计；
   - `queue_job_with_input_artifact()` 是否先校验权限和外部 artifact，再把非空请求 payload 保存为 `ArtifactKind.JOB_INPUT`，并把 `job_payload` 与外部输入引用一起写入 `Job.input_artifact_ids`；
   - Streamlit 缺少所选方案 hourly detail 时，是否只在当前用户可提交项目任务且存在 `technical_summary`、`config_snapshot`、三条 `input_curve_*` artifact 时显示/提交后台补算；重复点击是否复用同一研究/方案的活动任务提示，而不是排出一串重复 job；
   - `execute_next_worker_job()`、`execute_worker_loop()`、`pilot-admin run-worker-once` 和 `pilot-admin run-worker-loop` 是否只执行受支持的 `technical_study/hourly_detail` 与 `economic_study/annual_cashflow` job；前者是否复用 `run_hourly_detail_for_scenario()` 并写回 `ArtifactKind.HOURLY_DETAIL`，后者是否读取 `technical_summary` / `recommendation_inputs` 并只为所选方案写回 `ArtifactKind.ANNUAL_CASHFLOW`；失败时是否标记 failed 而不是卡在 running；`run-worker-loop` 的 `max_jobs` / `idle_exit_after` 是否能让脚本安全退出；
   - `LocalJobStore.claim_next_queued_job()`、`PilotAccessService.claim_next_job_for_worker()`、`update_worker_job_progress()`、`succeed_worker_job()`、`fail_worker_job()`、`pilot-admin claim-next-job`、`heartbeat-job`、`complete-worker-job` 和 `fail-worker-job` 是否只更新任务元数据、校验 worker、支持任务类型过滤，并跳过归档项目；命令是否明确不执行真实计算；
   - `pilot-admin list-audit-events` 和平台管理页“审计日志”是否只能由平台管理员读取，并能分别抽查全局审计和项目级审计；
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

### 5.1 UI 审查与切片选择提示词

```text
请先做一次“Streamlit UI 提升审查与切片选择”，暂时不要改代码。

目标用户：
内部能源项目规划人员、技术经济测算人员和项目负责人。界面应像工程测算和规划辅助决策后台，而不是营销首页或展示型网站。

请先阅读：
- AGENTS.md 中的 UI、经济性和推荐原则；
- docs/WEB_APP_WORKFLOW_AND_UI_RESTRUCTURE.md；
- docs/ui/audit-20260606-product-design/UI_AUDIT_REPORT.md；
- docs/ui/audit-20260606-product-design/UI_REDESIGN_ROADMAP.md；
- docs/ui/audit-20260606-product-design/FLOW_CAPTURE_NOTES.md；
- docs/ui/UI_IMPLEMENTATION_MAPPING_20260606.md；
- docs/ui/UI_MAPPING_SELF_AUDIT_20260608.md；
- docs/ui/UI_REFERENCE_MAPPING.md；
- docs/ui/gpt-project-handoff-20260609/01_PROJECT_CONTEXT.md；
- docs/ui/gpt-project-handoff-20260609/02_UI_REVIEW_PROMPT.md；
- docs/ui/gpt-project-handoff-20260609/05_SCREENSHOT_AND_RECORDING_CHECKLIST.md；
- docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/SCREENSHOT_INDEX.md；
- docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md；
- src/green_direct/ui/app.py；
- src/green_direct/visualization/chart_ui.py。

如果可以运行本地应用，请启动：
streamlit run src/green_direct/ui/app.py

然后用浏览器实际检查 01-06 页，至少覆盖桌面宽屏和窄屏/手机宽度。窄屏建议至少检查约 `390 x 844` 或接近手机浏览器宽度。若当前环境无法打开浏览器，请说明限制，并基于已有截图和代码审查，不要臆造浏览器已通过。历史截图只能作为线索，不能替代当前运行截图；如果代码已变更，应重新截图或明确“未重新截图”。

如果本地启用了 pilot auth，请先用仓库现有脚本或 `pilot-admin bootstrap` 建临时测试账号；不要为了 UI 截图关闭多用户门禁或把 `GREEN_DIRECT_ENABLE_PILOT_AUTH=0` 当成公网内测默认。UI 审查应覆盖登录后项目选择/创建、六步工作流和平台管理入口的可见性边界。

目标体验按页面拆解：
1. 01 项目启动：让用户快速知道输入是否齐备、结果是否可用、下一步该做什么；
2. 02 方案仿真：让曲线上传、方案池、政策约束、性能设置更清晰，避免把全量枚举表作为主入口；
3. 03 经济测算：提高参数分组和输入密度，减少大面积空白和反复 rerun；
4. 04 方案推荐：强化推荐席位、命中理由、风险提示和关键技术经济指标；
5. 05 图表概览：围绕代表方案和用户加入的对比方案组织图表，而不是围绕全部枚举结果；
6. 06 下载报告：清楚展示哪些文件已准备好、哪些需要先运行计算、导出失败如何处理。

重点先判断这些已知问题是否仍存在：
1. 窄屏/手机宽度下侧边导航、顶部状态条或卡片是否遮挡主内容；
2. 03 经济性页的主 CTA 是否仍被大量参数挤到首屏之外，计算完成后是否缺少结果摘要回馈；
3. 04 推荐页推荐理由是否被截断，`ok / warning / pending / no_candidate` 状态是否有清楚视觉分级；
4. 05 图表页每张主图是否说明自己回答的问题，指定方案加入后用户是否知道影响哪些图；
5. 06 下载报告页是否有“交付包/依赖状态”概念，能否说明哪些导出已准备好、哪些需要先补算；
6. 上传控件、错误提示和导出状态在窄屏下是否仍清楚，上传上限提示是否与 `GREEN_DIRECT_MAX_UPLOAD_MB` / Streamlit `server.maxUploadSize` 一致；
7. UI 是否仍把 raw scenario enumeration、逐小时大表或年度现金流大表放回主体验。

首轮可选小切片建议：
1. 窄屏/手机宽度可用性：解决侧边导航或顶部状态条遮挡主内容，让同事移动网络访问时至少能完成登录、选择项目和 Demo 试算；
2. 03 经济测算首屏节奏：让关键参数、计算按钮、运行状态和计算后摘要更靠近，减少用户误以为页面卡住；
3. 04 推荐页状态表达：强化推荐席位、命中理由、pending/no-candidate 的原因和下一步动作；
4. 06 导出中心交付状态：把已准备、需补算、无权限、失败重试分清楚，尤其要体现不可导出用户边界；
5. 图表页代表方案复核：减少围绕全量枚举的选择压力，让图表回答“为什么推荐/风险在哪”。

若没有强 P0/P1 上线风险，建议第一轮 UI 落地优先选第 1 项或第 2 项；不要一次性重做全部六页。

首轮 UI 小切片不要做：
1. 不要把 Streamlit 改成 Next.js/React，也不要为了 Vercel 首发重写前端；
2. 不要新增营销首页、hero 页或装饰性大图；
3. 不要把图表/导出/推荐做成需要全量逐小时明细常驻的路径；
4. 不要绕过现有项目、成员、导出权限和审计服务层。

输出要求：
1. 先列 UI Findings，按 P0/P1/P2 排序；
2. 每个 finding 给出页面、复现路径、相关代码区域和用户影响；
3. 提出 3-5 个可独立实施的小切片，每个切片说明要改的用户任务、主要文件、风险、测试/浏览器验收方式；
4. 推荐本轮最应该落地的 1 个小切片；
5. 明确哪些建议必须等 review/debug P0/P1 清零后再做。
6. 给出需要保存的新截图清单，包含桌面和窄屏，说明建议存放到 `docs/ui/audit-YYYYMMDD-*/screenshots/` 或复用现有 UI evidence 目录。
```

### 5.2 UI 小切片落地提示词

```text
请在不改变核心计算口径的前提下，落地上一轮 UI 审查中选出的一个小切片。

如果没有上一轮审查结果，请先执行“UI 审查与切片选择提示词”，不要直接大改代码。

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
7. 不要把 mock 数据接入正式 Streamlit 计算链路；mock 只允许留在 docs/ui/ 原型中并明确标注。

交付要求：
1. 每个 UI 改动都说明对应的用户任务；
2. 给出修改文件清单；
3. 运行 python -m pytest -q；
4. 用浏览器实际打开本地 Streamlit，检查六个页面；如果改动涉及响应式布局，还要检查窄屏/手机宽度；
5. 截图或文字记录检查结果；
6. 如果发现 UI 问题但本轮不修，请列为 P2/P3 后续项；
7. 如果改动改变了重要用户体验判断，请更新 notes/PRODUCT_POLISH_LOG.md；如果会影响下一位 agent 的工作边界，请更新 notes/HANDOFF_FOR_NEW_MACHINE.md。

浏览器验收最低要求：
1. 桌面宽屏打开 01-06 页，确认主 CTA、状态提示和页面跳转没有明显异常；
2. 窄屏/手机宽度打开至少 01 项目启动、02 方案仿真和本轮改动页，确认没有导航、状态条、按钮或卡片遮挡主内容；
3. 如果改动涉及经济性、推荐或导出状态，至少用 Demo 跑到相关页面并记录计算前、计算中/排队、计算后的状态；
4. 如果本轮改动涉及上传或部署提示，确认上传控件显示的大小上限与应用策略一致，默认应为 20MB；
5. 如果当前环境无法截图，必须说明不能截图的原因，并列出人工验收路径。
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
4. AuditLog，包括 `pilot-admin list-audit-events` 和平台管理页“审计日志”这类本地抽查入口与未来正式审计后台的边界；
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

## 8. 托管平台部署演练提示词

```text
请做一次“受控公网内测托管平台部署演练”审查。目标是尽快把当前 Streamlit + Docker 应用放到公网邀请制测试，但不要为了适配平台重写核心计算或 UI。

请先阅读：
- README_DEPLOY.md
- render.yaml
- docs/MANAGED_PUBLIC_BETA_DEPLOYMENT.md
- docs/MOBILE_NETWORK_TRIAL_CHECKLIST.md
- docs/PUBLIC_BETA_DEPLOYMENT_AUDIT.md
- SECURITY.md
- Dockerfile
- docker-compose.yml
- .env.example
- scripts/preflight_internal_pilot_deploy.py
- scripts/smoke_streamlit_app.py

判断边界：
1. 当前应用是长运行 Streamlit Python Web 进程，不适合直接部署到 Vercel Functions 或 Cloudflare Pages/Workers 作为主机；
2. 短期推荐容器/PaaS 托管应用本体，Cloudflare 负责 DNS、HTTPS、Access 和入口防护；
3. 如果要改架构，优先把本地 store 换成数据库/对象存储和后台 worker，再考虑前端重写。

请检查：
1. `render.yaml` 是否与 Dockerfile、健康检查、端口、环境变量和 `/data/pilot_store` 一致；
2. `render.yaml` 是否显式部署 `codex/UI` pilot 分支、保持 `numInstances=1`，并设置 `autoDeployTrigger: checksPass`，避免部署默认分支或未通过质量门的提交；
3. `GREEN_DIRECT_ENABLE_PILOT_AUTH=1` 和 `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0` 是否在托管平台默认生效；
4. persistent disk 是否挂载到 `/data`，pilot store 是否不在 Git 仓库路径；
5. 平台管理员 bootstrap 命令是否明确在 Render Web Service Shell 中执行，且没有误用无法访问同一 persistent disk 的 One-Off Job；
6. Cloudflare Access 门禁与应用内登录是否形成双层门禁；
7. 重启后用户、项目、任务、结果和审计日志是否仍可保留；
8. 备份/恢复、日志脱敏、上传文件大小、导出权限和不可导出用户是否有实测清单。

如果你可以访问托管平台或本机 Docker，请实际执行：
0. python scripts/preflight_internal_pilot_deploy.py --run-smoke
0a. 如有可用 pilot store，运行 python scripts/preflight_internal_pilot_deploy.py --pilot-store-dir <pilot_store> --json
0b. 推送到 GitHub 后运行 python scripts/preflight_internal_pilot_deploy.py --require-git-sync
1. docker compose build
2. docker compose up -d
3. 创建平台管理员
4. 登录，创建项目，运行一个最小样例
5. docker compose restart 后确认数据仍存在
6. docker compose down

如果不能访问托管平台，请只做仓库内配置审查，不要臆造已经部署成功。

输出：
1. P0/P1/P2 findings；
2. 可直接修复的小配置问题；
3. 仍需人工在平台控制台完成的步骤；
4. 建议的公网内测域名、Access 策略和回滚方案。
```
