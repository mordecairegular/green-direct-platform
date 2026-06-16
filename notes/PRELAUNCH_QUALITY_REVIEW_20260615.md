# 上线前质量审查记录（2026-06-15）

## 审查基线

- 当前分支：`codex/UI`
- 对比基线：`origin/codex/UI`
- 当前状态：本地已有连续 checkpoint；本记录随 Streamlit 项目工作区、项目成员管理、项目级结果持久化、最小任务/结果索引/下载/summary-only 恢复面板、input artifact 留存、跨会话单方案明细补算、经济 summary-only 恢复、推荐席位输入恢复和推荐 portfolio-only 恢复补充更新。
- 目标口径：近期上线应理解为受控内部试用 / pilot；若开放公网访问，也只能按邀请制“受控公网内测 Route A”推进，不应理解为公网生产 SaaS。

## 本轮 checkpoint 概览

本轮已把原先未提交工作整理为连续 checkpoint，核心变化包括：

- UI 大改造、方案图谱、经济性参数工作台与导出体验；
- 大批量汇总优先 summary-only 路径、当前会话与基于 input artifact 的跨会话单方案逐小时明细按需补算、可选并行技术仿真；
- 经济性批量评价性能优化；
- 内部试用后台模型、结果存储、账号注册表、认证、可选 Streamlit 登录门禁、项目工作区门禁、最小平台账号/项目成员管理页、管理员服务、任务状态存储、权限审计门面，技术/经济 summary/推荐席位输入/推荐 portfolio 持久化第一阶段，以及欢迎页任务/结果索引、已落盘 artifact 下载、技术 summary-only 恢复、经济 summary-only 恢复、推荐席位输入恢复和推荐 portfolio-only 恢复面板；
- `pilot-admin` 命令行账号管理入口；
- Artifact payload 留存清理第一版；
- 内部试用 `.env.example`、部署 runbook 和 pilot store 备份/恢复脚本第一版；
- 面向 Claude Code 的内部试用审查 / 后台架构 prompt 和跨机器 handoff 文档；
- 已吸收用户补充的受控公网内测讨论稿方向：不接真实电力控制系统、不开放社会化注册、保留项目/Run/Artifact/AuditLog、后端控制导出权限、补文件安全和部署恢复边界。

近期 checkpoint 已覆盖 CLI、认证、平台管理、项目工作区、大批量汇总优先模式，技术仿真 summary/config/input curves、经济性 summary、推荐席位输入、推荐 portfolio 写入项目级 `ResultStore`，项目内最近任务/结果索引、已落盘 artifact 下载、技术 summary-only 恢复、经济 summary-only 恢复、推荐席位输入恢复、推荐 portfolio-only 恢复、已有 hourly artifact 加载、input artifact 恢复补算，到期 artifact payload 清理，以及内部试用部署/备份/恢复第一版材料；具体提交以 `git log --oneline` 为准。

## 验证结果

已执行：

```powershell
python -m pytest -q
python -m compileall -q src scripts tests
$env:PYTHONPATH = "src"; python -m green_direct.cli pilot-admin --help
```

结果：

- 全量测试通过：293 项通过；
- `src scripts tests` 编译检查通过；
- 源码树下 CLI 启动口径验证通过；
- `git diff --check` 没有实际空白错误，仅有 Windows 换行转换提示；
- 本轮 input artifact 跨会话明细补算 checkpoint 已提交为 `3ce2222 feat(pilot): restore input artifacts for detail recompute`；随后已补经济 summary-only 和推荐 portfolio-only 恢复 checkpoint，提交以 `git log --oneline` 为准。

## 结论

项目目前不建议直接对外公网生产发布。

在受控条件下，可以进入内部 10-20 人 pilot：

- 只部署在内网、VPN 或可信机器；
- 明确告知用户经济性 V1 是方案筛选 / 排序辅助，不是最终投资决策模型；
- 不上传敏感正式数据，或先建立数据目录权限和备份策略；
- 服务器部署不要启用本地运行快照；
- 大批量算例先按汇总优先试用，图表和报告只围绕已有逐小时明细或当前会话可按需补算明细的方案开展。

若要从内网/VPN pilot 进一步开放为公网可访问内测，应先补齐 Route A 的 P0 条件：邀请制账号、可导出/不可导出用户权限、后端导出校验、文件上传限制、仓库外产物存储、日志脱敏、HTTPS/反向代理、数据卷备份和回滚说明。当前已有 `docs/INTERNAL_PILOT_DEPLOYMENT_RUNBOOK.md` 和 pilot store 备份/恢复脚本第一版，但还不是完整公网生产部署体系。

## 主要风险

### P0：公网生产阻塞

1. Streamlit 主 UI 已有可选登录门禁、最小项目工作区门禁和平台账号/项目成员管理页，但还不是正式权限系统。
   设置 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1` 后，未登录用户不能进入六步工作流；登录用户必须先创建或选择有效项目；切换项目会清理当前测算结果和下载缓存；平台管理员可在“平台管理”中创建账号、重置密码、停用账号、授予/撤销平台管理员、查看会话，并维护项目成员角色。技术仿真 summary/config snapshot/input curves、经济性 summary、推荐席位输入和推荐 portfolio 已能写入项目级 `ResultStore`，欢迎页也能展示项目最近任务/结果索引、加载下载已落盘 artifact，并把技术 summary-only 恢复为当前会话结果；同一 `study_id` 的技术 summary 已恢复后，也可把经济 summary 恢复为当前会话内的摘要型经济结果并同步恢复推荐席位输入，把推荐 portfolio 恢复为当前会话内的推荐结果；图表/报告入口可加载已有 hourly artifact，或在 input artifact 未过期且快照包含 `curve_columns` 时重建 `TechnicalStudyInput` 并补算单方案明细。但正式上线前仍必须接入更正式的会话/数据库适配、CSRF/反向代理安全边界，并继续迁移年度现金流、完整历史结果恢复、推荐视角选择/重新排序工作台状态、图表/报告和导出产物持久化。

2. 可导出/不可导出用户权限已有第一版 membership 授权位，但仍不是正式下载服务。
   `ProjectMembership.can_export_artifacts` 已能独立于项目角色控制 artifact payload 读取，最小平台管理页也可维护该字段；欢迎页历史产物下载和 06 导出页会在禁止导出时拦截，`PilotAccessService.read_artifact_payload()` 会对成功和拒绝的下载尝试写入审计。受控公网内测前仍需把未来 API、图表/报告项目级 artifacts、数据库适配和反向代理下载入口全部接到同一授权策略。

3. 没有正式后台任务队列和 worker。
   当前重计算仍发生在 Streamlit 进程内，PNG ZIP 使用进程内后台线程，技术/经济/推荐 Job 也是计算完成后的同步状态登记。`LocalJobStore` 只是任务状态契约，不会真正调度 worker。多人同时大算例时缺少排队、取消、限流、重试和失败恢复。

4. 本地 JSON 文件 store 没有事务、锁和备份策略。
   账号、会话、任务和结果服务适合作为 pilot 语义骨架，但不是正式数据库。并发写入、磁盘损坏、机器迁移和权限隔离都需要 SQLite/Postgres 或对象存储适配器解决。

5. 上传文件已有第一层类型/大小门禁，技术三曲线 input artifact 与 artifact payload 过期清理已有第一版，但数据留存仍未达到公网内测级闭环。
   Streamlit 上传入口已限制允许后缀和默认 20MB 单文件大小，技术仿真配置快照会记录上传文件名、大小和 SHA256；技术三曲线会在项目结果保存时写入默认 30 天过期的 `ArtifactKind.INPUT_CURVE`，并支持历史 summary-only 恢复后的单方案明细补算；`JobArtifact` 已能记录 `retention_policy`、`expires_at`、`purged_at`，`pilot-admin purge-expired-artifacts` 可由平台管理员清理到期 payload 并写入 `DELETE_ARTIFACT` 审计。但仍需要覆盖价格曲线、经济性年度现金流、图表包和报告文件，避免普通日志记录原始曲线或服务器内部路径，并实现关键 Run 保留机制和定时调度。

6. 部署策略已补内部试用 runbook，但仍不是完整生产部署。
   当前已有 `.env.example`、`docs/INTERNAL_PILOT_DEPLOYMENT_RUNBOOK.md`、`scripts/backup_pilot_store.ps1` 和 `scripts/restore_pilot_store.ps1`，可覆盖环境变量、首个管理员、启动、备份、恢复、清理、冒烟和回滚边界；但仍缺系统服务守护、集中日志、监控告警、HTTPS/反向代理样例、CI/CD、健康检查和自动化恢复演练。

### P1：内部试用前应重点观察

1. 大批量汇总优先模式已能避免为未保留方案构造完整 `hourly_detail`，并已支持当前会话和历史 summary-only 恢复后的单方案逐小时明细按需补算。
   未保留方案会走 summary-only 技术仿真路径，已降低大批量筛选耗时和内存压力；推荐页、图表概览页和导出/报告页会先加载已有项目级 hourly artifact，再尝试用当前 session 的 `TechnicalStudyInput` 或历史 input artifact 恢复出的 `TechnicalStudyInput` 补算，并把补算结果写回项目级 hourly artifact。剩余风险是这仍是同步 Streamlit 动作，不是后台 Job，也没有 worker 级进度、取消和重试。

2. 电价曲线经济性依赖逐小时明细。
   当前大批量部分保留明细时会切回固定价 / 网页组价模式。这是安全降级，但用户需要明确知道价格曲线不会参与这类大批量经济测算。

3. 图表模块仍是原型型展示层。
   目前可用于 pilot 交流和核查，但不应作为长期架构锚点。后续应围绕推荐方案和按需明细重做图表/报告。

4. `pilot-admin` CLI 仍是 bootstrap、应急运维和过期 artifact 清理入口。
   最小 Streamlit 平台管理页已经可维护账号和项目成员，但首个管理员创建、密码应急重置、过期 payload 清理和服务器端排障仍需要 CLI 或后续独立后台。

5. 欢迎页“项目任务与结果”仍不是完整历史结果页。
   它可以帮助内部试用用户确认当前项目已有任务和结果记录，下载已落盘的 summary / portfolio artifact，并 summary-only 恢复技术汇总；同一 `study_id` 的技术汇总已恢复后，也可 summary-only 恢复电源侧/同一主体经济汇总并同步恢复已保存的推荐席位输入，并 portfolio-only 恢复推荐组合；图表/报告入口可加载已有 hourly artifact 或从 input artifact 恢复输入后补算单方案明细。但它仍不能恢复完整历史 `StudyResult`、年度现金流、推荐视角选择/重新排序工作台状态，不能删除结果、标记报告版本或跨项目搜索。

### P2：后续质量改进

- 增加端到端冒烟：启动 Streamlit、加载样例、跑技术仿真、跑经济性、进入推荐和导出页；
- 固化大批量性能基准样例，记录方案数、耗时、内存和是否保留逐小时明细；
- 增加本地 store 并发写入测试或尽快替换为数据库；
- 把第一版 runbook 继续升级为可执行部署包：HTTPS/反向代理示例、系统服务配置、日志轮转、健康检查、备份演练和回滚演练。

## 给下一轮 Claude Code 的审查重点

建议让 Claude Code 按以下顺序继续：

1. 先读 `AGENTS.md`、`CLAUDE.md`、`notes/HANDOFF_FOR_NEW_MACHINE.md`、`notes/PRODUCT_POLISH_LOG.md`、`docs/INTERNAL_PILOT_ARCHITECTURE_PLAN.md` 和本文档；
2. 运行 `python -m pytest -q` 和 `python -m compileall -q src`；
3. 重点审查 `src/green_direct/ui/app.py` 是否存在跨用户状态、旧结果复用、价格曲线误用、导出缓存串会话；
4. 重点审查 `src/green_direct/services/` 下本地后台服务的权限边界、路径校验、审计记录和失败场景；
5. 重点审查受控公网内测 Route A 缺口：不可导出用户是否还能通过未来 API、项目级报告 artifact、缓存或反向代理路径绕过下载，普通用户是否能猜测他人 project/run/artifact，上传文件是否还能绕过大小/类型/schema 门禁，日志是否可能泄露原始曲线；
6. 设计并实现下一阶段最小闭环：完整任务状态页 + 历史结果恢复/下载/删除 + 按需补算后台 Job 化 + 图表/报告项目级 artifacts + 部署 runbook 实机演练。
