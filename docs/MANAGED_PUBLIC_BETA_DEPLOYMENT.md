# 托管平台公网内测部署路线

日期：2026-06-16

本文用于把当前 Streamlit + Docker 项目快速放到公网做邀请制内测。目标是借助成熟平台能力，不自研 HTTPS、边缘入口、基础监控和容器托管。

## 1. 推荐结论

当前项目不建议直接部署到 Vercel 或 Cloudflare Pages/Workers 作为主机。

原因：

- 当前应用是长运行 Streamlit Python Web 进程，不是静态站点或短生命周期 serverless function；
- 当前 pilot 项目库使用本地持久化 store，需要持久磁盘或后续数据库/对象存储；
- 计算任务可能持续数十秒到数分钟，不适合边缘函数/普通 serverless 请求模型；
- 06 导出和图表包依赖 Python 包、Chromium/Kaleido 等运行时，容器环境更稳。

推荐公网测试路线：

```text
Browser
  -> Cloudflare DNS / HTTPS / Access
  -> Render/Fly.io/Railway/Cloud Run container service
  -> Green Direct Streamlit Docker container
  -> Persistent disk or managed database/object storage
```

第一选择：`Render Web Service + persistent disk + render.yaml`。

Cloudflare 的最佳角色：域名、HTTPS、WAF/基础防护、Zero Trust Access、访问日志入口。不要让 Cloudflare Workers/Pages 承载当前 Python 计算应用本体。

当前仓库已有最小后台 worker loop，但 `render.yaml` 仍只创建 Web Service。原因是本地 file store 版依赖 `/data/pilot_store`，不应在 Render 上直接再建一个独立 Worker Service 并假设它能共享同一个服务磁盘。若要拆成 Web + Worker 两个托管服务，优先把项目库迁移到 Postgres/SQLite 托管盘方案和对象存储；若部署在自有 VM / Docker Compose，可用同一命名卷启动可选 `green-direct-worker` profile。

如果目标只是让同事在手机或移动网络下先试用，请优先按 `docs/MOBILE_NETWORK_TRIAL_CHECKLIST.md` 执行；本文保留更完整的平台判断和架构边界。

## 2. 为什么先选 Render

Render 对当前仓库的改动最小：

- 已有 `Dockerfile`；
- 已有 `.dockerignore`，会排除本地 runtime、日志、输出、历史归档、测试和文档材料，减少托管平台构建上下文；
- 新增 `render.yaml` 后可用 Blueprint 创建服务；
- 支持 Docker Web Service；
- 支持持久磁盘挂载到 `/data`；
- 可直接健康检查 `/_stcore/health`；
- 可绑定自定义域名，再交给 Cloudflare 管理 DNS/Access。

注意：持久磁盘通常不是免费能力。若只做一次性无数据保留演示，可以不用持久盘；但真实 10-20 人内测必须保留 pilot store。

## 2.1 GitHub Import 与 Vercel 的边界

把项目放到 GitHub 是推荐动作。后续无论使用 Render、Fly.io、Railway、Cloud Run、Streamlit Community Cloud 还是 Vercel，都应通过 GitHub 私有仓库做版本管理、审查、回滚和自动部署。

但 Vercel 的 `Import Git Repository` 不适合作为当前应用的直接部署方式：

- Vercel 更适合 Next.js、静态前端和 serverless/API functions；
- 当前项目入口是 `streamlit run src/green_direct/ui/app.py`，需要一个持续运行的 Python Web 进程；
- 当前项目需要 `/data/pilot_store` 这类持久化项目库，而不是请求结束即释放的函数运行环境；
- 当前测算可能持续较久，且导出依赖 Python 运行时、Chromium/Kaleido 和本地 artifact 文件。

因此本项目的“GitHub + 快速部署”建议写成：

```text
GitHub private repository
  -> Render Blueprint import
  -> Dockerfile build
  -> persistent disk /data
  -> Cloudflare Access 控制外部访问
```

Vercel 可以作为未来正式化后的前端托管平台：例如将前端改为 Next.js，再让后端 API、worker、数据库和对象存储独立部署。但这不是第一次公网试用的低成本路径。

## 3. Render 部署步骤

1. 把当前分支推到 GitHub/GitLab。
2. 推送前运行 `python scripts\preflight_internal_pilot_deploy.py --run-smoke`，确认部署配置、本地服务器口径和 `/_stcore/health` 都通过。
3. 推送后运行 `python scripts\preflight_internal_pilot_deploy.py --require-git-sync`，确认本地分支与 upstream 同步。
4. 在 Render 新建 Blueprint，选择本仓库。
5. Render 读取仓库根目录 `render.yaml`，创建 `green-direct-internal-pilot`。
6. 确认环境变量：
   - `GREEN_DIRECT_ENABLE_PILOT_AUTH=1`
   - `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0`
   - `GREEN_DIRECT_PILOT_STORE_DIR=/data/pilot_store`
   - `GREEN_DIRECT_MAX_UPLOAD_MB=20`
   - `GREEN_DIRECT_MAX_SCENARIOS_PER_RUN=20000`
   - `GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD=1000`
   - `GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT=20`
   - `PORT=8503`，或使用平台默认端口；Docker 启动命令会优先读取 `PORT`
7. 确认 persistent disk 挂载：
   - mount path: `/data`
   - app store: `/data/pilot_store`
8. 部署完成后访问 Render 默认域名，确认登录页出现。
9. 用 Render Shell 初始化平台管理员。不要用 Render One-Off Job 初始化本地 file store 版 pilot store；持久盘应在 Web Service 运行环境中访问。

```bash
GREEN_DIRECT_ADMIN_PASSWORD='replace-with-one-time-password' \
python -m green_direct.cli pilot-admin bootstrap \
  --store-dir /data/pilot_store \
  --user-id admin \
  --login-name admin@example.local \
  --display-name "平台管理员" \
  --password-env GREEN_DIRECT_ADMIN_PASSWORD
```

10. 登录后立刻重置强密码，并创建第一批内测用户。

若要在自有 VM 或 Docker Compose 环境中启用最小后台 worker，管理员初始化完成后启动：

```bash
docker compose --profile worker up -d green-direct-worker
```

托管平台 Render 的本地 disk 路线下，首次内测可先用同步补算 fallback、在平台管理页“任务运维”手动处理一个排队任务，或在同一服务 shell 中执行一次性 `run-worker-once` 做排障；不要把本地 file store 版误拆成多个无法共享状态的服务。
当前最小 worker 覆盖按需逐小时明细和固定价/网页组价按需年度现金流；逐时价格曲线现金流、全量技术仿真、全量经济性、图表包和完整报告仍未后台化。

## 4. Cloudflare 入口

建议把 Render 自定义域名接入 Cloudflare：

1. 在 Render 添加自定义域名，例如 `green-direct.example.com`。
2. 在 Cloudflare DNS 添加对应 CNAME。
3. 开启 HTTPS。
4. 在 Cloudflare Zero Trust Access 中创建 self-hosted application：
   - 域名：`green-direct.example.com`
   - 策略：只允许指定邮箱、邮箱域或一次性邀请列表；
   - 内测期不要开放社会化注册。

这样会形成双层门禁：

- Cloudflare Access：公网入口第一层，仅邀请用户可进入；
- 应用内 pilot auth：第二层，控制项目、成员和导出权限。

## 5. 替代平台

Fly.io：适合容器和 volume，全球节点选择灵活；需要熟悉 `flyctl` 和 volume/机器配置。

Railway：上手快，适合试用；使用 volume 时要确认当前套餐和备份策略。

Google Cloud Run：容器托管成熟，但不适合继续依赖容器本地持久文件作为唯一数据层；更推荐搭配 Cloud SQL/GCS 后再用于下一阶段。

Streamlit Community Cloud / Hugging Face Spaces：适合公开 demo 或非敏感样例数据，不建议作为当前项目的真实内测主环境。

## 6. 如果决定改架构

可以改，但建议分两阶段：

第一阶段仍保留 Streamlit 前台，把本地 store 接口后面换成托管数据库和对象存储：

```text
Streamlit UI
  -> PilotAccessService / ResultStore / JobStore
  -> Postgres or SQLite managed database
  -> Object storage for input curves, hourly detail, chart packages, reports
  -> Worker process for long-running calculations (`run-worker-loop` or managed queue worker)
```

第二阶段再把前台改为 Next.js/React，把计算和项目库变成 FastAPI + worker + queue。这个路线更接近正式 SaaS，但会明显拉长工期，不适合作为第一次公网试用的前置条件。

## 7. 上线前最小验收

- 登录页可通过公网访问，未登录不能进入六步工作流；
- Cloudflare Access 只允许邀请用户进入；
- 管理员已创建至少一个可导出用户和一个不可导出用户；
- 不可导出用户无法下载 06 页临时导出和已落盘 artifact；
- 普通用户不能看到其他项目；
- 创建项目、运行一次小样例、保存结果、重启服务后项目仍存在；
- 下载和关键操作可在平台管理页“审计日志”或 CLI 审计抽查中查到；
- `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0`；
- `GREEN_DIRECT_PILOT_STORE_DIR` 不在 Git 仓库目录内；
- 备份/恢复至少演练一次。

## 8. 仍然不能省略的边界

即使用成熟平台托管，当前版本仍只能作为受控公网内测：

- 不接真实电力控制系统；
- 不开放公开注册；
- 不上传高度敏感生产数据；
- 不承诺正式投资决策、接入批复或交易结算结果；
- 不把本地 JSON store 视为长期正式数据库；
- 不把同步 Streamlit 计算视为正式后台队列。
