# Green Direct 内部试用部署说明

本文面向内部 10-20 人试用和邀请制受控公网内测 Route A。它不是正式公网 SaaS 部署手册；正式对外前仍需要后台 worker、数据库/对象存储适配、监控告警和安全复核。

## 1. 产品边界

本工具仅用于绿电直连 / 微电网项目前期方案测算、政策指标初判和方案比选辅助。

禁止把本工具部署或宣传为：

- EMS、SCADA、调度自动化或生产控制系统；
- 实时运行平台；
- 真实电表、保护装置、储能 PCS、发电设备或负荷控制接口；
- 项目审批、接入批复、交易结算或绿证核发依据。

## 2. Docker 快速启动

构建镜像：

```powershell
docker compose build
```

初始化第一个平台管理员。请使用一次性强密码，不要把密码写入仓库：

```powershell
$env:GREEN_DIRECT_ADMIN_PASSWORD = "change-me-before-use"
docker compose run --rm `
  -e GREEN_DIRECT_ADMIN_PASSWORD `
  green-direct `
  python -m green_direct.cli pilot-admin bootstrap `
    --store-dir /data/pilot_store `
    --user-id admin `
    --login-name admin@example.local `
    --display-name "平台管理员" `
    --password-env GREEN_DIRECT_ADMIN_PASSWORD
Remove-Item Env:\GREEN_DIRECT_ADMIN_PASSWORD
```

启动服务：

```powershell
docker compose up -d
```

本机访问：

```text
http://localhost:8503
```

查看日志：

```powershell
docker compose logs -f green-direct
```

停止服务：

```powershell
docker compose down
```

## 2.1 托管平台快速公网测试

如果目标是尽快做邀请制公网内测，优先使用成熟平台承载公网入口和容器运行，不建议把当前 Streamlit 应用直接部署到 Vercel 或 Cloudflare Pages/Workers 作为主机。当前应用是长运行 Python Web 进程，并依赖本地 pilot store；更适合 Docker Web Service + 持久磁盘。

推荐路线：

```text
Cloudflare DNS / HTTPS / Access
  -> Render Web Service
  -> Dockerfile
  -> persistent disk mounted at /data
```

仓库已提供 `render.yaml`，可在 Render 中用 Blueprint 创建服务。详细步骤见 `docs/MANAGED_PUBLIC_BETA_DEPLOYMENT.md`。

如果目标是让同事用手机或移动网络尽快试用，请直接按 `docs/MOBILE_NETWORK_TRIAL_CHECKLIST.md` 执行。

推送到 GitHub 或触发托管平台部署前，建议先做一次本地服务器口径冒烟检查：

```powershell
python scripts\smoke_streamlit_app.py
```

该脚本会启用 pilot 登录门禁、关闭 runtime snapshot、使用临时 pilot store，启动 Streamlit 并检查 `/_stcore/health`，成功或失败后都会自动停止进程。

也可以运行完整部署 preflight：

```powershell
python scripts\preflight_internal_pilot_deploy.py --run-smoke
```

preflight 会检查部署文件、GitHub Actions 质量门、Docker/Render 安全默认值、`.dockerignore`、持久盘路径和可选 Streamlit smoke。

推送到 GitHub 后、在 Render 部署前，可再运行：

```powershell
python scripts\preflight_internal_pilot_deploy.py --require-git-sync
```

该检查会确认当前工作树干净，且当前分支与 upstream 同步，避免 Render 部署到旧提交。

仓库包含 `.github/workflows/internal-pilot-quality.yml`。推送或提交 PR 后，GitHub Actions 会自动运行 compile、部署 preflight 和全量 pytest；手动触发该 workflow 并勾选 `run_smoke` 时，还会启动 Streamlit 做 `/_stcore/health` 冒烟检查。Render 首次部署或重要回滚前，应先确认该质量门通过。

## 3. 默认安全设置

`docker-compose.yml` 默认设置：

```text
GREEN_DIRECT_ENABLE_PILOT_AUTH=1
GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0
GREEN_DIRECT_PILOT_STORE_DIR=/data/pilot_store
GREEN_DIRECT_MAX_UPLOAD_MB=20
GREEN_DIRECT_MAX_SCENARIOS_PER_RUN=20000
GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD=1000
GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT=20
PORT=8503
```

含义：

- 用户必须登录后才能进入六步工作流；
- 多人部署不启用本地 runtime snapshot，避免恢复上一位用户结果；
- 账号、会话、项目、任务、结果、artifact 和审计日志写入容器外 volume；
- 上传文件默认单文件 20MB 上限。
- 技术仿真默认单次最多 20,000 个候选方案，超过时前台会阻止启动，后端 `run_batch()` 也会拒绝执行。
- 经济性默认在超过 1,000 个方案时进入 summary-first：仍计算全量汇总、FIRR/NPV 和推荐排序，但只常驻前 20 个方案的年度现金流，避免公网试用环境一次生成过多现金流表。
- 容器默认监听 8503；托管平台如注入 `PORT`，Docker 启动命令会优先使用平台端口。

## 4. 数据卷

Compose 使用命名卷：

```text
green_direct_pilot_store -> /data/pilot_store
```

该目录保存：

- 用户和本地密码 hash；
- 会话 token hash；
- 项目和项目成员；
- Job 状态；
- 技术/经济/推荐 summary artifact；
- artifact 元数据和 payload；
- 审计日志。

不要把该数据卷内容提交到 Git，也不要放到 Web 静态目录。

## 4.1 后台 Worker

按需逐小时明细补算、按需年度现金流补算已经可以提交为项目级 queued job。完成平台管理员 bootstrap 后，可启动可选 worker profile，让后台进程持续认领受支持任务：

```powershell
docker compose --profile worker up -d green-direct-worker
```

默认 worker 使用 `admin` 作为平台管理员 actor，worker id 为 `pilot-worker-compose`。可通过环境变量覆盖：

```powershell
$env:GREEN_DIRECT_WORKER_ACTOR_USER_ID = "admin"
$env:GREEN_DIRECT_WORKER_ID = "pilot-worker-1"
$env:GREEN_DIRECT_WORKER_POLL_INTERVAL_SECONDS = "5"
docker compose --profile worker up -d green-direct-worker
```

该 worker 当前只执行 `technical_study/hourly_detail` 和 `economic_study/annual_cashflow` 任务。后者仅支持固定价/网页组价经济性结果，逐时价格曲线结果需等价格曲线 artifact 化后再补。它不是正式队列系统，不提供 worker 级取消、重试、资源隔离或多 worker 并发锁；本地 JSON store 版试用期建议最多启动一个 worker。

如果使用 Render 这类只部署单个 Web Service 的首次试用环境，暂时不要把本地 file store 版拆成独立 Worker Service。平台管理员可以在应用内“平台管理 -> 任务运维”手动处理一个排队任务；这会在当前 Streamlit Web 进程内复用同一套 `execute_next_worker_job()` 链路，适合排障和小任务补算。该页面也可以把超时 running 任务元数据标记为 failed。两者都不是自动后台队列，也不会终止真实操作系统进程。

## 5. 账号与权限

平台管理员登录后可以在“平台管理”页：

- 创建用户；
- 重置密码；
- 停用用户；
- 授予/撤销平台管理员；
- 创建/归档项目；
- 维护项目成员角色；
- 控制项目成员是否允许下载/导出结果；
- 在“任务运维”中查看排队/运行中任务，手动处理一个受支持的 queued job，并恢复超时 running 任务元数据；
- 在“审计日志”中只读查看全局或项目级审计事件，并按动作筛选。

当前项目角色为 `admin`、`analyst`、`viewer`，导出权限由 `can_export_artifacts` 独立控制。不可导出用户应能查看网页结果，但不能下载 artifact 或 06 页导出文件。

## 6. 反向代理与 HTTPS

受控公网内测必须放在 HTTPS 反向代理后。推荐拓扑：

```text
Browser
  -> HTTPS:443
  -> Caddy/Nginx
  -> http://127.0.0.1:8503 or http://green-direct:8503
```

Caddy 示例：

```caddyfile
green-direct.example.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8503
}
```

Nginx 示例：

```nginx
server {
    listen 443 ssl http2;
    server_name green-direct.example.com;

    ssl_certificate     /etc/letsencrypt/live/green-direct.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/green-direct.example.com/privkey.pem;

    client_max_body_size 25m;

    location / {
        proxy_pass http://127.0.0.1:8503;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
    }
}
```

公网访问时不要直接暴露 8503 到互联网；应只允许反向代理或 VPN 网关访问容器端口。

## 7. 备份

备份命名卷到本地目录：

```powershell
New-Item -ItemType Directory -Force .\backups | Out-Null
docker run --rm `
  -v green_direct_pilot_store:/data/pilot_store:ro `
  -v ${PWD}\backups:/backup `
  alpine `
  sh -c "cd /data && tar czf /backup/green-direct-pilot-store-$(date +%Y%m%d-%H%M%S).tgz pilot_store"
```

建议：

- 每天自动备份一次；
- 重要试用前手动备份；
- 定期把备份恢复到临时目录演练；
- 备份文件不得提交到 Git。

## 8. 恢复

恢复前先停服务并备份当前卷：

```powershell
docker compose down
```

恢复到一个新卷更安全：

```powershell
docker volume create green_direct_pilot_store_restored
docker run --rm `
  -v green_direct_pilot_store_restored:/data `
  -v ${PWD}\backups:/backup `
  alpine `
  sh -c "cd /data && tar xzf /backup/green-direct-pilot-store-YYYYMMDD-HHMMSS.tgz"
```

核查无误后，再切换 compose volume 名称或把恢复内容复制到正式卷。不要在未备份的情况下覆盖现有数据卷。

## 9. 过期清理

清理到期 artifact payload：

```powershell
docker compose run --rm green-direct `
  python -m green_direct.cli pilot-admin purge-expired-artifacts `
    --store-dir /data/pilot_store `
    --actor-user-id admin
```

当前清理能力只覆盖已登记的 artifact payload。原始上传文件、逐小时明细、图表包和报告导出的完整项目级留存闭环仍在后续路线中。

## 10. 健康检查与冒烟

容器健康检查访问：

```text
http://127.0.0.1:8503/_stcore/health
```

每次发布后至少检查：

- 未登录用户只能看到登录页；
- 平台管理员可登录并进入“平台管理”；
- 普通用户只能看到授权项目；
- 禁止导出的成员不能下载历史 artifact 或 06 页导出文件；
- Demo 技术仿真、经济测算、推荐、图表和导出页可打开；
- 日志不包含明文密码、token、原始曲线和服务器敏感路径。

## 11. 回滚

推荐流程：

1. 备份当前 `green_direct_pilot_store`；
2. 记录当前镜像 tag 或 commit；
3. 切回上一份已验证源码或镜像；
4. 启动服务后做冒烟检查；
5. 如果新版本写入了旧版本不认识的 metadata，先在恢复副本上验证旧版本能否读取关键结果。

不要用删除数据卷的方式回滚代码问题。

## 12. 仍未完成

当前 Docker 部署包解决的是“可标准化启动和持久化本地 store”。尚未完成：

- 正式队列 / worker 级取消 / 重试 / 进程守护；当前仅有按需逐小时明细和固定价/网页组价年度现金流的 queued job 提交入口、one-shot worker 和最小轮询 worker；
- SQLite/Postgres 或对象存储适配；
- 原始上传文件、逐小时明细、图表包和报告导出的完整 artifact 留存；
- 集中日志、监控告警、CI/CD 和自动化恢复演练；
- 正式企业 IAM、OIDC/LDAP、CSRF 防护和安全扫描。
