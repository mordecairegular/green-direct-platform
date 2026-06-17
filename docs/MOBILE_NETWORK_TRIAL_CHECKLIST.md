# 同事移动网络试用清单

日期：2026-06-16

目标：让内部同事不在同一局域网、只用手机或移动网络，也能访问并试用绿电直连测算工具。

首次发布请先按 `docs/PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md` 做负责人短操作单；需要完整上下文时，再按 `docs/PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md` 从本地检查、GitHub 推送、Render 部署、管理员 bootstrap 到 Cloudflare Access 顺序执行。本文聚焦发给真实同事前的移动网络验收。

## 0. 当前最短路径

当前仓库已经配置了 GitHub 远端、Docker 部署文件、Render Blueprint、部署 preflight、Streamlit smoke 和 GitHub Actions 质量门。要让同事用移动网络试用，下一步不是把 Streamlit 改成 Vercel 应用，而是：

1. 经项目负责人确认后，把本地 `codex/UI` 分支推送到 GitHub 私有仓库。
2. 等 GitHub Actions `Internal Pilot Quality Gate` 跑通。
3. 在 Render 选择 Blueprint / Import Git Repository，导入同一个 GitHub 仓库和分支。
4. 确认 Render 创建的是 Docker Web Service，部署分支为 `codex/UI`，`autoDeployTrigger=checksPass`，并挂载 `/data` persistent disk。
5. 在 Render Web Service Shell 先运行 `pilot-admin doctor --store-dir /data/pilot_store --json`，通过后再初始化平台管理员。
6. 登录应用创建 3-5 个首批内测账号。
7. 把 Render 自定义域名接入 Cloudflare DNS / HTTPS / Access，只放行内测邮箱。
8. 用手机 4G/5G 完成第 6 节验收后，再把链接发给真实同事。

如果未来把前台改成 Next.js/React，Vercel 可以成为前端托管平台；但当前第一版公网试用仍以 Render 承载 Streamlit/Docker 应用本体，Cloudflare 做入口门禁。

如果当天公网平台卡住但需要先让同事试用完整功能，可临时发送本地试用包。发送前运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_local_trial_package.ps1
```

然后发送 `release/GreenDirectLocalTrial_YYYYMMDD.zip`。本地包保留当前网页工作流，但每台电脑本地运行一份，不提供公网多人访问、统一账号后台或移动网络共享入口。

## 1. 推荐路径

```text
GitHub private repository
  -> Render Blueprint 部署 Docker 应用
  -> Render persistent disk 保存 /data/pilot_store
  -> Cloudflare DNS / HTTPS / Access
  -> 同事通过手机浏览器访问域名
  -> 应用内账号登录
```

不要把当前项目直接导入 Vercel 作为主机。Vercel 的 GitHub Import 适合 Next.js/静态站/serverless API；当前工具是 Streamlit 长进程和本地 pilot store，更适合容器托管。

## 2. 发布前准备

- GitHub 私有仓库已创建；
- 推送前本地 `python scripts\preflight_internal_pilot_deploy.py --run-smoke` 已通过，且 `git-tracked:*` 检查没有发现私有 `.env`、本地运行状态、数据库/日志/压缩包或超大文件；
- 如需快速判断当前发布卡点，可运行 `python scripts\preflight_internal_pilot_deploy.py --summary`；它只输出发布就绪总览、失败项和下一步建议；
- 当前分支已推送；
- 推送后已运行 `python scripts\preflight_internal_pilot_deploy.py --require-git-sync`，确认当前分支、GitHub upstream 和 `render.yaml` 部署分支一致且同步；
- 如果只给人看，不给 CI 归档，可使用 `python scripts\preflight_internal_pilot_deploy.py --require-git-sync --summary`；
- 已运行 `python scripts\preflight_internal_pilot_deploy.py --require-github-private`，或已在 GitHub 页面人工确认仓库 visibility 为 Private；
- GitHub Actions `Internal Pilot Quality Gate` 已通过；如本次是首次部署或重要回滚，手动触发该 workflow 并勾选 `run_smoke`；
- 仓库包含 `Dockerfile`、`render.yaml`、`requirements-runtime.txt`；
- `.dockerignore` 已排除 `.github/`、`.runtime/`、日志、输出目录、历史归档、测试目录、docs/notes 等运行镜像不需要的内容；
- 本地已运行 `python scripts\preflight_internal_pilot_deploy.py --run-smoke`，确认部署配置、GitHub 推送源安全检查和服务器口径健康检查都通过；
- 首次 bootstrap 和创建第一批账号后，已按 `docs/PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md` 做一次 pilot store 备份，并恢复到空目录通过 `pilot-admin doctor`；
- Render 账户可访问该 GitHub 仓库；
- Cloudflare 已接管或可管理试用域名；
- 决定一个内测域名，例如 `green-direct.example.com`；
- 准备第一批同事邮箱名单；
- 准备平台管理员一次性强密码。

## 3. Render 部署

1. 在 Render 选择 Blueprint / Import Git Repository。
2. 选择 GitHub 私有仓库。
3. 确认 Render 读取根目录 `render.yaml`。
4. 确认服务类型为 Web Service，runtime 为 Docker。
5. 确认分支和部署闸：
   - branch: `codex/UI`
   - auto deploy: checks pass
   - instances: `1`
6. 确认 persistent disk：
   - mount path: `/data`
   - app store: `/data/pilot_store`
7. 确认关键环境变量：登录门禁为 `1`，runtime snapshot 为 `0`，单次技术方案数上限为 `20000`，默认并行技术仿真进程数为 `1`，经济性现金流保留阈值为 `1000`，保留数量为 `20`。
8. 部署完成后，访问 Render 默认域名。
9. 若显示应用登录页，说明公网入口已通。
10. 在 Render Web Service Shell 运行 `pilot-admin doctor --store-dir /data/pilot_store --json`，确认 persistent disk、JSON metadata、payload 写入、协作锁和审计 JSONL 都正常。

当前 `render.yaml` 只创建 Web Service。按需逐小时明细和固定价/网页组价年度现金流后台任务已有 `run-worker-loop`，但本地 file store 版在 Render 上不应简单拆成另一个独立 Worker Service 共享 `/data/pilot_store`；该类持久盘绑定在服务侧，正式拆分 worker 前应先迁移到数据库/对象存储，或改用同一主机/Compose 共享卷方案。第一次移动网络试用可先保留同步补算 fallback；必要时平台管理员可在应用内“平台管理 -> 任务运维”手动处理一个排队任务，也可在同一服务环境里执行 `run-worker-once`。

## 4. 初始化管理员

在 Render Web Service 的 Shell 中执行。不要用 Render One-Off Job 初始化本地 file store 版 pilot store；持久盘应在 Web Service 运行环境中访问。

```bash
GREEN_DIRECT_ADMIN_PASSWORD='replace-with-one-time-password' \
python -m green_direct.cli pilot-admin bootstrap \
  --store-dir /data/pilot_store \
  --user-id admin \
  --login-name admin@example.local \
  --display-name "平台管理员" \
  --password-env GREEN_DIRECT_ADMIN_PASSWORD
```

随后登录应用，立刻重置管理员密码，并创建内测用户。

建议第一批账号：

- 1 个平台管理员账号；
- 1 个可导出测试账号；
- 1 个不可导出测试账号；
- 3-5 个真实同事账号，先小范围试。

## 5. Cloudflare Access

1. 在 Render 添加自定义域名。
2. 在 Cloudflare DNS 添加 CNAME。
3. 开启 HTTPS。
4. 在 Cloudflare Zero Trust Access 创建 self-hosted application：
   - 域名：试用域名；
   - 策略：只允许指定邮箱或邮箱域；
   - 禁止公开注册；
   - 可设置登录有效期，例如 24 小时或 7 天。

Cloudflare Access 是公网入口第一层门禁；应用内账号是第二层门禁。两层都保留。

## 6. 发给同事前的验收

请至少完成以下检查：

- 手机 4G/5G 网络可打开试用域名；
- 非白名单邮箱无法通过 Cloudflare Access；
- 白名单邮箱通过 Access 后仍需应用内账号登录；
- 未登录用户不能进入六步工作流；
- 可导出用户能下载自己的项目结果；
- 不可导出用户不能下载 06 页导出和 artifact；
- 普通用户看不到其他人的项目；
- 创建项目、运行小样例、重启服务后项目仍存在；
- 首次备份文件已保存到 Git 仓库外的受控位置，恢复演练目录的 `pilot-admin doctor` 返回 `status=pass`；
- Render Shell 中 `pilot-admin doctor --store-dir /data/pilot_store --json` 返回 `status=pass`；
- 平台管理页“审计日志”和 CLI 审计抽查都能看到登录、项目、下载、artifact 操作；
- 如测试后台逐小时明细或年度现金流补算，确认 queued job 会出现在欢迎页任务面板，并由平台管理页“任务运维”、`run-worker-once` 或 `run-worker-loop` 处理完成；
- `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0`；
- `GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS=1` 已按内测机器资源确认；如调到 2-4，应先完成 benchmark，避免多人试用时 CPU/RAM 被抢满；
- `GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD=1000`、`GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT=20` 已按内测资源配置确认；
- 数据目录不是 Git 仓库目录。
- Render/Docker 构建日志中没有上传本地 `.runtime`、输出文件、历史归档或调试日志。
- 本地 smoke、Render health check 和 Cloudflare 入口检查都通过后，再发给真实同事。

## 7. 发给同事的说明

建议说明：

```text
这是绿电直连测算工具的邀请制内测环境，仅用于前期方案测算、政策指标初判和功能反馈。

请不要上传高度敏感或正式生产数据。工具不连接、不控制任何真实电力设备，也不作为正式审批、接入批复、交易结算或投资决策依据。

首次访问需要先通过 Cloudflare 邮箱验证，再使用管理员分配的工具账号登录。
```

## 8. 发现问题时记录

同事反馈问题时，优先使用 `docs/PUBLIC_BETA_FEEDBACK_TRIAGE.md` 中的模板和 P0/P1/P2 分级。至少记录：

- 用户账号；
- 项目名称；
- 大致时间；
- 手机/电脑；
- 浏览器；
- 操作到第几步；
- 错误提示截图；
- 是否可复现；
- 是否涉及上传文件或导出文件。

不要让同事通过聊天工具发送原始敏感曲线文件。需要排查时，由管理员在项目审计和 artifact 元数据中定位。
