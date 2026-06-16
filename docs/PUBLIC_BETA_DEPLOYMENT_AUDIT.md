# 受控公网内测部署审计矩阵

日期：2026-06-16

本文把用户提供的《绿电直连测算工具公网内测版准备方案（Codex 执行稿）》映射到当前仓库状态。结论用于指导后续 10-20 人多人访问 / 受控公网内测 Route A，不表示正式公网 SaaS 已就绪。

## 1. 总结结论

当前项目可以继续作为受控内部 pilot checkpoint 推进，但距离“公网可访问的邀请制内测环境”仍有 P0 工程缺口。

已具备：

- 可选登录门禁、平台管理员 bootstrap、账号创建/停用/重置密码；
- 项目、项目成员和 `can_export_artifacts` 第一版授权位；
- 本地 `PilotAccessService` 权限/审计门面；
- 本地 `ResultStore`、`JobStore`、artifact 元数据和过期 payload 清理；
- 技术 summary、按需单方案逐小时明细、经济 summary、推荐席位输入和推荐 portfolio 的项目级写入第一阶段；技术 summary、经济 summary、推荐席位输入和推荐 portfolio 已有 summary-only / portfolio-only 恢复入口；
- 导出页已可将所选方案 HTML 图表包和简版 Markdown 报告显式保存为项目级 `chart_package` / `report` artifact，登记 `chart_export` / `report_export` Job，并写入 `STORE_ARTIFACT` 审计；
- 当前 06 导出页的临时下载按钮已接入 `PilotAccessService.record_transient_export_download()`，点击 CSV/Excel/ZIP/Markdown 下载会复用项目导出权限并写 `DOWNLOAD_ARTIFACT` 审计；
- 上传文件类型/大小校验和 hash 元数据；
- 大方案池 summary-first、计算前粗略耗时提示、大批量确认、单次方案数硬上限、可选并行和并行方案块提交、当前会话单方案逐小时明细补算、hourly artifact 留存、已有 hourly artifact 跨会话加载，以及基于三条 input artifact 的跨会话单方案明细补算第一版；
- 欢迎页项目任务与结果面板，以及排队/运行中任务的最小查看和取消入口；
- `.env.example`、内部部署 runbook、pilot store 备份/恢复脚本。
- Dockerfile、docker-compose.yml、README_DEPLOY.md、SECURITY.md 第一版。

仍未达到公网内测 Route A：

- Docker 部署包仍是本地文件 store 版，缺少正式系统服务托管、日志轮转、监控告警和安全扫描；
- HTTPS/反向代理已有文档样例，但仍未经过目标服务器实机演练；
- 技术仿真三条输入曲线已能随技术结果保存为 input artifact，历史 summary-only 结果可在 input artifact 未过期且 `config_snapshot` 带有 `curve_columns` 时恢复 `TechnicalStudyInput` 并补算单方案逐小时明细；HTML 图表包和 Markdown 报告已有显式保存第一版，但 PNG/Excel/批量包、价格曲线、完整报告和未来 API/反向代理下载尚未完整进入项目/Run 级 artifact 留存闭环；
- input artifact 补算仍是 Streamlit 进程内同步动作，不是后台 Job；旧结果若缺少 `curve_columns` 或 input artifact 已清理，只能查看 summary 或已有 hourly artifact；
- 计算仍主要在 Streamlit 进程内同步执行；已有活动任务查看/取消入口，但没有后台 worker、队列、worker 级取消和重试闭环；
- 本地 JSON 文件 store 没有数据库事务、锁和并发写保护。

## 2. P0 审计矩阵

| 要求 | 当前状态 | 证据 | 风险 | 下一步 |
|---|---|---|---|---|
| 只有登录用户可以上传和计算 | 部分满足 | `GREEN_DIRECT_ENABLE_PILOT_AUTH=1` 后未登录用户只能看到登录表单 | 默认开发模式仍不启用登录；公网部署必须强制启用 | 部署 runbook 和容器入口强制设置 pilot auth |
| 管理员创建/停用用户 | 第一版满足 | `LocalPilotAdminService`、`pilot-admin`、Streamlit 平台管理页 | 仍是本地文件版账号后台 | 后续迁移 SQLite/Postgres 或统一身份 |
| 用户只能访问授权项目 | 第一版满足 | `PilotAccessService.list_accessible_projects()` 和项目工作区门禁 | 未来 API/下载入口必须复用同一门面 | 禁止 UI 直接绕过 `PilotAccessService` |
| 不可导出用户不能导出 | 第一版满足 | `ProjectMembership.can_export_artifacts`、`read_artifact_payload()` 下载审计；当前 06 页临时下载走 `record_transient_export_download()`；网页查看走 `read_artifact_payload_for_view()` | 仍需保证未来 API、反向代理下载和对象存储签名 URL 不绕过服务门面 | 所有下载/导出统一走后端授权服务 |
| 上传文件类型/大小限制 | 第一版满足 | `UploadPolicy`，默认 20MB，CSV/XLSX/XLSM 白名单；技术三曲线随技术结果写入 `ArtifactKind.INPUT_CURVE` | 价格曲线、schema 报告和原始输入清理调度仍未闭环 | 增加 schema 报告、定时清理和关键 Run 保留 |
| 单次方案数限流 | 第一版满足 | `GREEN_DIRECT_MAX_SCENARIOS_PER_RUN`、`PerformanceParams.max_scenarios_per_run`、02 页超限提示、大批量确认和 `run_batch()` 后端拒绝 | 粗略耗时模型仍需目标服务器实测校准；已有活动任务取消入口，但仍缺 worker 级取消和排队 | 继续补后台进度、worker 取消和任务队列 |
| 项目/Run/参数/结果摘要留存 | 部分满足 | 技术/经济/推荐 summary、推荐席位输入、已保留的经济年度现金流与按需 hourly artifact 已写 `ResultStore`；HTML 图表包和 Markdown 报告可显式保存为 `chart_package` / `report` artifact；技术 summary、经济 summary、年度现金流、推荐席位输入和推荐 portfolio 可恢复到当前会话 | 推荐视角选择/重新排序工作台状态、PNG/Excel/批量导出包和完整报告未完整持久化；summary-only 经济运行不会凭空恢复未保留现金流 | 按 `StudyResultRecord` 串联完整结果索引并补剩余 chart/report/export artifacts |
| 原始文件、逐小时明细、导出文件留存和清理 | 部分满足 | 当前有 artifact payload 过期清理；技术三曲线 input artifact 与按需 hourly artifact 默认 30 天过期；HTML 图表包和 Markdown 报告默认 7 天过期；已有 hourly artifact 可跨会话加载，缺明细的历史 summary-only 可在 input artifact 可用时恢复输入并补算单方案明细 | 补算与导出保存仍是同步动作；价格曲线、PNG/Excel/批量包未完整 artifact 化；旧结果缺 `curve_columns` 时不能恢复输入 | 把按需补算升级为 Job，并补剩余 cashflow/chart/report/export artifacts |
| 关键操作审计日志 | 部分满足 | 登录、项目、成员、任务、artifact 写入/网页查看/下载/清理、当前 06 页临时导出下载已审计 | 管理员跨项目查看、原始文件查看、未来 API/反向代理下载仍需补齐 | 扩充 `AuditAction` 覆盖面 |
| Docker 可部署 | 第一版满足 | `Dockerfile`、`docker-compose.yml`、`README_DEPLOY.md` | 尚未在目标服务器完成构建/启动/恢复演练 | 实机运行 `docker compose build/up` 和数据卷恢复演练 |
| HTTPS/反向代理/备份/恢复/回滚说明 | 部分满足 | 内部 runbook、PowerShell 备份/恢复脚本、`README_DEPLOY.md` | 缺少系统服务托管、集中日志、监控告警和自动恢复演练 | 在目标服务器补 Caddy/Nginx 配置、日志和监控 |
| 核心算法回归通过 | 满足当前 checkpoint | 最近 `pytest -q` 为 298 passed | 后续改性能/后台时仍需重复验证 | 每个工程化切片后跑回归 |

## 3. 推荐执行顺序

1. **部署包演练**
   - 在目标服务器或等效 Linux 环境运行 `docker compose build`、`docker compose up -d`；
   - 验证容器默认启用 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1`；
   - 验证数据目录通过仓库外 volume 挂载，重启后账号和项目不丢失；
   - 结合目标域名补 Caddy/Nginx HTTPS 配置和日志策略。

2. **项目级 artifact 闭环**
   - 原始上传文件保存为 input artifact；
   - 当前会话按需补算的技术逐小时明细已第一版保存为 hourly artifact；
   - 已保留的经济年度现金流保存为 `annual_cashflow` ZIP artifact，并可随经济 summary 恢复；
   - 推荐席位输入已随经济 summary 保存为 `recommendation_inputs.json`，后续仍需保存视角选择和重新排序工作台状态；
   - HTML 图表包和 Markdown 报告已可显式保存为 export/report artifact；后续补 PNG/Excel/批量包和完整报告；
   - 所有 artifact 统一 retention、hash、size、audit。

3. **历史结果恢复**
   - 从 `StudyResultRecord` 恢复技术 summary、经济 summary、已保留年度现金流、推荐席位输入和推荐 portfolio；推荐视角选择与重新排序状态后续再恢复为完整工作台状态；
   - 如果已有 hourly artifact，优先按网页查看权限加载到当前工作流；
   - 如果 input artifact 可用，允许跨会话按需补算某方案 hourly detail；
   - 如果 input artifact 已清理，明确提示“只能查看摘要，不能补算明细”。

4. **后台 Job**
   - 技术仿真、经济性测算、图表包和报告导出从同步按钮变成真正后台 Job；
   - 欢迎页已有活动任务查看和取消入口第一版，下一步应让前台轮询真实 worker 状态；
   - worker 写入 `ResultStore`，失败写脱敏错误。

5. **数据库/并发**
   - 内部 10-20 人可先评估 SQLite；
   - 若公网可访问，优先规划 PostgreSQL；
   - 本地 JSON store 继续作为开发和小范围演示适配器，不作为长期并发存储。

## 4. 给 Claude Code 的审计补充

让 Claude Code review/debug 时，应把本文件作为 spec source，与 `docs/CLAUDE_CODE_INTERNAL_PILOT_PROMPTS.md` 和 `docs/PERFORMANCE_OPTIMIZATION_PLAN.md` 一起使用。

建议固定审查口径：

```text
请对照 docs/PUBLIC_BETA_DEPLOYMENT_AUDIT.md 中的 P0 审计矩阵，逐项确认当前仓库是否已经满足。
如果发现矩阵中“部分满足/不满足”的项目已有新实现，请更新矩阵并给出文件与测试证据。
如果直接修复 P0/P1，请保持小切片，不改变 V0.1 技术调度口径、经济性 V1 口径或推荐 V1 排序口径。
```
