# 受控公网内测首次发布作战单

日期：2026-06-17

用途：把当前仓库从本地开发状态，推进到“内部同事可用手机或移动网络访问”的首次受控公网内测。本文是执行顺序清单，不替代 `docs/MANAGED_PUBLIC_BETA_DEPLOYMENT.md` 的平台判断，也不替代 `docs/MOBILE_NETWORK_TRIAL_CHECKLIST.md` 的发给同事前验收。

目标范围：

- 10-20 人内部邀请制试用；
- GitHub 私有仓库作为代码源；
- Render Docker Web Service 承载当前 Streamlit 长进程；
- Render persistent disk 保存 `/data/pilot_store`；
- Cloudflare DNS / HTTPS / Access 作为公网入口第一层门禁；
- 应用内 pilot auth 作为第二层账号和项目权限门禁。

非目标：

- 不是正式公网 SaaS；
- 不开放公开注册；
- 不接 EMS、SCADA、调度自动化、真实电力设备或生产控制网络；
- 不把本地 JSON store 视为长期正式数据库；
- 不把当前同步计算和最小 worker 当作正式队列系统。

## 0. 发布角色

发布执行人：

- 本地执行检查、提交、推送；
- 在 Render 创建服务并查看部署日志；
- 在 Cloudflare 配置域名和 Access。

平台管理员：

- 在 Render Web Service Shell 中运行 `pilot-admin doctor` 和 `pilot-admin bootstrap`；
- 登录应用创建内测账号；
- 抽查审计日志、项目权限和导出权限。

试用同事：

- 只通过 Cloudflare Access 和应用账号登录；
- 不上传高度敏感或正式生产数据；
- 反馈问题时提供项目、时间、浏览器、截图和复现步骤。

## 1. 本地发布前

确认当前分支是 `codex/UI`：

```powershell
git status --short --branch
```

运行本地部署预检和服务器口径冒烟：

```powershell
python scripts\preflight_internal_pilot_deploy.py --run-smoke
```

如本机已经准备了真实试用 store，也可以把 store doctor 纳入同一条检查：

```powershell
python scripts\preflight_internal_pilot_deploy.py --pilot-store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR --run-smoke
```

确认没有未提交改动：

```powershell
git status --short
```

如本轮改了代码、部署脚本或质量门，至少运行相关测试；首次发布前推荐跑全量：

```powershell
python -m pytest -q
```

## 2. 推送到 GitHub

经项目负责人确认后，推送当前内测分支：

```powershell
git push origin codex/UI
```

推送后立刻确认本地、GitHub upstream 和 Render 配置分支一致：

```powershell
python scripts\preflight_internal_pilot_deploy.py --require-git-sync
```

该命令必须通过后再让 Render 部署。若失败：

- `git:clean` 失败：还有未提交改动，先提交或暂存；
- `git:branch` 失败：当前本地分支不是 `render.yaml` 配置的部署分支；
- `git:upstream-branch` 失败：当前分支跟踪的 upstream 不是 Render 部署分支；
- `git:sync` 失败：本地和 GitHub 仍不同步，先 push 或 pull。

等待 GitHub Actions `Internal Pilot Quality Gate` 通过。首次部署或重要回滚时，手动触发该 workflow 并勾选 `run_smoke`。

## 3. Render 创建服务

在 Render 中选择 Blueprint / Import Git Repository，导入同一个 GitHub 私有仓库。

确认 Render 读取仓库根目录 `render.yaml`，并逐项核对：

- service name: `green-direct-internal-pilot`;
- runtime: Docker;
- branch: `codex/UI`;
- dockerfile: `./Dockerfile`;
- health check: `/_stcore/health`;
- auto deploy: checks pass;
- instances: `1`;
- persistent disk mount path: `/data`;
- pilot store: `/data/pilot_store`;
- `GREEN_DIRECT_ENABLE_PILOT_AUTH=1`;
- `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0`;
- `GREEN_DIRECT_MAX_SCENARIOS_PER_RUN=20000`;
- `GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD=1000`;
- `GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT=20`.

首次部署完成后，先访问 Render 默认域名。预期结果：

- 能看到登录页；
- 未登录不能进入六步工作流；
- Render health check 为 healthy。

## 4. 初始化项目库和管理员

在 Render Web Service Shell 中运行。不要用无法访问同一 persistent disk 的 One-Off Job 初始化本地 file store 版 pilot store。

先检查 store：

```bash
python -m green_direct.cli pilot-admin doctor \
  --store-dir /data/pilot_store \
  --json
```

只有 `status=pass` 时才继续。若失败，先修复 persistent disk 挂载、目录权限或损坏 metadata。

初始化首个平台管理员：

```bash
GREEN_DIRECT_ADMIN_PASSWORD='replace-with-one-time-password' \
python -m green_direct.cli pilot-admin bootstrap \
  --store-dir /data/pilot_store \
  --user-id admin \
  --login-name admin@example.local \
  --display-name "平台管理员" \
  --password-env GREEN_DIRECT_ADMIN_PASSWORD
```

随后登录应用，立刻重置管理员强密码，并创建第一批账号：

- 1 个备用平台管理员；
- 1 个可导出测试账号；
- 1 个不可导出测试账号；
- 3-5 个真实同事账号。

## 5. Cloudflare 入口

在 Render 添加自定义域名，例如 `green-direct.example.com`。

在 Cloudflare DNS 添加 CNAME，指向 Render 给出的目标域名，并开启 HTTPS。

在 Cloudflare Zero Trust Access 创建 self-hosted application：

- application domain: 试用域名；
- policy: 仅允许指定邮箱、邮箱组或公司域名；
- session duration: 内测期可设 24 小时到 7 天；
- 禁止公开注册和匿名访问。

保留双层门禁：

```text
Cloudflare Access
  -> 应用内 pilot auth
  -> 项目成员和导出权限
```

## 6. 发链接前手机验收

用手机 4G/5G 网络完成以下检查：

- 非白名单邮箱无法通过 Cloudflare Access；
- 白名单邮箱通过 Access 后仍需应用内账号登录；
- 未登录不能进入六步工作流；
- 可导出测试账号能下载自己的项目结果；
- 不可导出测试账号不能下载 06 页临时导出或 artifact；
- 普通用户看不到其他项目；
- 创建项目、运行小样例、保存结果；
- 重启 Render 服务后，项目、用户和结果索引仍存在；
- Render Shell 中 `pilot-admin doctor --store-dir /data/pilot_store --json` 仍为 `status=pass`；
- 平台管理页“审计日志”能看到登录、项目、下载、artifact 相关事件；
- Render/Docker 构建日志没有上传本地 `.runtime`、输出目录、历史归档或调试日志。

这些检查通过后，再把链接发给真实同事。

## 7. 发给同事的话

建议使用以下说明：

```text
这是绿电直连测算工具的邀请制内测环境，仅用于前期方案测算、政策指标初判和功能反馈。

请不要上传高度敏感或正式生产数据。工具不连接、不控制任何真实电力设备，也不作为正式审批、接入批复、交易结算或投资决策依据。

首次访问需要先通过 Cloudflare 邮箱验证，再使用管理员分配的工具账号登录。
```

## 8. 故障和回滚

如果 Render 部署失败：

- 先看 GitHub Actions 是否通过；
- 再看 Render build log 和 health check；
- 本地复跑 `python scripts\preflight_internal_pilot_deploy.py --run-smoke`；
- 不要为了临时通过而关闭 `GREEN_DIRECT_ENABLE_PILOT_AUTH` 或启用 runtime snapshot。

如果登录页能打开但管理员无法登录：

- 在 Render Web Service Shell 运行 `pilot-admin doctor --store-dir /data/pilot_store --json`；
- 确认 bootstrap 是在 Web Service Shell 中执行；
- 必要时用 `pilot-admin list-users`、`reset-password`、`enable-user` 和 `revoke-session` 排查。

如果计算或导出失败：

- 记录用户、项目、时间、浏览器、操作步骤和截图；
- 平台管理员抽查审计日志和任务列表；
- 对 queued job，可在平台管理页“任务运维”手动处理一个受支持任务，或在同一服务环境中运行 `run-worker-once` 排障。

如果需要回滚：

- 优先回滚到 GitHub 上最近一次通过 `Internal Pilot Quality Gate` 的提交；
- Render 重新部署回滚提交；
- 回滚前后都运行 `pilot-admin doctor --store-dir /data/pilot_store --json`；
- 若涉及数据损坏，先备份 `/data/pilot_store`，再执行恢复或清理。

## 9. 下一阶段改架构时机

当前首发路线以少改动为优先。以下情况出现后，再启动数据库化和前后端拆分：

- 同时在线人数或项目数超过本地 JSON store 的安全边界；
- 需要多个 Web 实例或独立 worker 服务；
- 需要正式任务队列、自动重试、worker 级取消或资源隔离；
- 需要更强审计、监控、备份恢复和权限治理；
- 计划把前台改为 Next.js/React 并部署到 Vercel。

建议演进顺序：

```text
LocalPilotRegistry / LocalJobStore / LocalResultStore 接口语义稳定
  -> SQLite/Postgres 适配器
  -> 对象存储保存曲线、逐小时明细、图表包和报告
  -> 正式 worker / queue
  -> FastAPI 后端
  -> Next.js/React 前端
```
