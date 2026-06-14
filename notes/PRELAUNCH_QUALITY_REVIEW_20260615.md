# 上线前质量审查记录（2026-06-15）

## 审查基线

- 当前分支：`codex/UI`
- 对比基线：`origin/codex/UI`
- 当前状态：本地工作区干净，分支比远端多 17 个 checkpoint。
- 目标口径：近期上线应理解为受控内部试用 / pilot，不应理解为公网生产 SaaS。

## 本轮 checkpoint 概览

本轮已把原先未提交工作整理为连续 checkpoint，核心变化包括：

- UI 大改造、方案图谱、经济性参数工作台与导出体验；
- 大批量汇总优先策略与可选并行技术仿真；
- 经济性批量评价性能优化；
- 内部试用后台模型、结果存储、账号注册表、认证、可选 Streamlit 登录门禁、最小平台账号管理页、管理员服务、任务状态存储和权限审计门面；
- `pilot-admin` 命令行账号管理入口；
- 面向 Claude Code 的内部试用审查 / 后台架构 prompt 和跨机器 handoff 文档。

最新两个 checkpoint：

- `2dc000f feat(cli): add pilot admin commands`
- `6a6ae63 docs: clarify pilot admin cli invocation`

## 验证结果

已执行：

```powershell
python -m pytest -q
python -m compileall -q src
$env:PYTHONPATH = "src"; python -m green_direct.cli pilot-admin --help
```

结果：

- 全量测试通过：243 项通过；
- `src` 编译检查通过；
- 源码树下 CLI 启动口径验证通过；
- `git diff --check` 没有实际空白错误，仅有 Windows 换行转换提示；
- 工作区已提交干净。

## 结论

项目目前不建议直接对外公网生产发布。

在受控条件下，可以进入内部 10-20 人 pilot：

- 只部署在内网、VPN 或可信机器；
- 明确告知用户经济性 V1 是方案筛选 / 排序辅助，不是最终投资决策模型；
- 不上传敏感正式数据，或先建立数据目录权限和备份策略；
- 服务器部署不要启用本地运行快照；
- 大批量算例先按汇总优先试用，图表和报告只围绕已有逐小时明细的方案开展。

## 主要风险

### P0：公网生产阻塞

1. Streamlit 主 UI 已有可选登录门禁和最小平台账号管理页，但还没有项目级权限。
   设置 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1` 后，未登录用户不能进入六步工作流；平台管理员可在“平台管理”中创建账号、重置密码、停用账号、授予/撤销平台管理员和查看会话。正式上线前仍必须接入项目列表、项目成员权限和更正式的会话/数据库适配。

2. 没有正式后台任务队列和 worker。
   当前重计算仍发生在 Streamlit 进程内，PNG ZIP 使用进程内后台线程。`LocalJobStore` 只是任务状态契约，不会真正调度 worker。多人同时大算例时缺少排队、取消、限流、重试和失败恢复。

3. 本地 JSON 文件 store 没有事务、锁和备份策略。
   账号、会话、任务和结果服务适合作为 pilot 语义骨架，但不是正式数据库。并发写入、磁盘损坏、机器迁移和权限隔离都需要 SQLite/Postgres 或对象存储适配器解决。

4. 部署策略仍是本地/桌面优先。
   当前启动脚本更适合 Windows 本机或演示机，缺少服务守护、日志、监控、HTTPS、反向代理、CI/CD、健康检查和恢复手册。

### P1：内部试用前应重点观察

1. 大批量汇总优先模式只常驻保留前 N 个生成序号方案的逐小时明细。
   这些方案不一定是推荐方案或经济排序靠前方案。后续应实现代表方案按需补算，或在排序后补保留推荐组合的逐小时明细。

2. 电价曲线经济性依赖逐小时明细。
   当前大批量部分保留明细时会切回固定价 / 网页组价模式。这是安全降级，但用户需要明确知道价格曲线不会参与这类大批量经济测算。

3. 图表模块仍是原型型展示层。
   目前可用于 pilot 交流和核查，但不应作为长期架构锚点。后续应围绕推荐方案和按需明细重做图表/报告。

4. `pilot-admin` CLI 是管理员 UI 前的运维入口。
   适合 bootstrap 和少量账号维护；后续必须接入 Streamlit 管理页或独立后台，不要长期要求业务管理员用命令行。

### P2：后续质量改进

- 增加端到端冒烟：启动 Streamlit、加载样例、跑技术仿真、跑经济性、进入推荐和导出页；
- 增加一个大批量性能基准样例，记录方案数、耗时、内存和是否保留逐小时明细；
- 增加本地 store 并发写入测试或尽快替换为数据库；
- 为内部试用部署写一份 runbook：启动、端口、环境变量、数据目录、备份、故障处理、回滚。

## 给下一轮 Claude Code 的审查重点

建议让 Claude Code 按以下顺序继续：

1. 先读 `AGENTS.md`、`CLAUDE.md`、`notes/HANDOFF_FOR_NEW_MACHINE.md`、`notes/PRODUCT_POLISH_LOG.md`、`docs/INTERNAL_PILOT_ARCHITECTURE_PLAN.md` 和本文档；
2. 运行 `python -m pytest -q` 和 `python -m compileall -q src`；
3. 重点审查 `src/green_direct/ui/app.py` 是否存在跨用户状态、旧结果复用、价格曲线误用、导出缓存串会话；
4. 重点审查 `src/green_direct/services/` 下本地后台服务的权限边界、路径校验、审计记录和失败场景；
5. 设计并实现下一阶段最小闭环：项目列表 + 项目权限拦截 + 任务状态页 + 结果存储接入。
