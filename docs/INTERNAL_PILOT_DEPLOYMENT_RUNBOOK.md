# 内部试用部署 Runbook

本文面向 10-20 人内部试用，不等同于正式公网 SaaS。公网可访问时也只能按邀请制受控内测 Route A 推进：不开公开注册，不接 EMS、SCADA、调度自动化、真实电表或生产控制网络。

## 1. 部署边界

允许：
- 内网、VPN 或受控反向代理后的 Streamlit 服务；
- 管理员创建账号，试用用户登录后选择项目工作区；
- 项目级技术 summary、经济 summary、推荐 portfolio、后台任务输入 artifact 和审计日志写入 `GREEN_DIRECT_PILOT_STORE_DIR`；
- 管理员定期备份 store、清理过期 artifact payload。

不允许：
- 把 `.runtime/latest_session_snapshot.pkl` 用于多人部署；
- 开放匿名访问或社会化注册；
- 把 pilot store 放在 Git 仓库、桌面临时目录或公开共享目录；
- 在日志中记录原始曲线、明文密码、明文 token 或敏感项目资料；
- 把经济性 V1 表述为最终投资决策结论。

## 2. 目录规划

推荐在服务器上准备三个目录，且都放在 Git 仓库外：

```text
D:\GreenDirectPilot\
├─ pilot_store\   # 账号、会话、项目、任务、结果和审计
├─ backups\       # pilot_store 压缩备份
└─ logs\          # Streamlit stdout/stderr 日志
```

Linux 或容器部署可使用同等含义的挂载目录，例如 `/srv/green-direct/pilot_store`。

Docker/compose 部署第一版见 `README_DEPLOY.md`。该入口默认启用登录门禁、关闭 runtime snapshot，并把 pilot store 挂载到容器外 volume。

## 3. 环境变量

以 `.env.example` 为准，内部试用至少需要：

```powershell
$env:GREEN_DIRECT_ENABLE_PILOT_AUTH = "1"
$env:GREEN_DIRECT_PILOT_STORE_DIR = "D:\GreenDirectPilot\pilot_store"
$env:GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT = "0"
$env:GREEN_DIRECT_MAX_UPLOAD_MB = "20"
$env:GREEN_DIRECT_MAX_SCENARIOS_PER_RUN = "20000"
$env:GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD = "1000"
$env:GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT = "20"
```

`START_GREEN_DIRECT_APP.bat` 和 `scripts/start_green_direct_app.ps1` 主要服务本地桌面体验。服务器或多人试用建议使用显式 Streamlit 命令，并确认 `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0`。
`GREEN_DIRECT_MAX_SCENARIOS_PER_RUN` 是多人试用阶段的同步计算护栏；默认 20,000 个候选方案，超过时前台和 `run_batch()` 后端都会拒绝本次任务。
`GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD` 和 `GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT` 控制经济性大批量年度现金流常驻策略；默认超过 1,000 个方案时只保留前 20 个方案的年度现金流表，经济性 summary、FIRR/NPV 和推荐排序仍按全量方案计算。

## 4. 安装与自检

```powershell
python -m pip install -r requirements.txt
python -m compileall -q src
python -m pytest -q
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin --help
```

如果服务器只跑试用服务，仍建议保留上述测试作为上线前 gate。

## 5. 首个管理员

首个管理员只能通过 CLI bootstrap：

```powershell
$env:PYTHONPATH = "src"
$env:GREEN_DIRECT_ADMIN_PASSWORD = "change-me-before-use"
python -m green_direct.cli pilot-admin bootstrap `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --user-id admin `
    --login-name admin@example.local `
    --display-name "平台管理员" `
    --password-env GREEN_DIRECT_ADMIN_PASSWORD
```

之后可在 Streamlit 的“平台管理”页创建试用账号、重置密码、停用/恢复用户、授予/撤销平台管理员、查看/撤销用户会话，并维护项目成员和导出权限。应至少保留两个活跃平台管理员，避免单点锁死。

CLI 也可作为 Web 管理页不可用时的服务器侧应急入口：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin list-projects `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin

python -m green_direct.cli pilot-admin list-sessions `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --user-id analyst_01

python -m green_direct.cli pilot-admin revoke-session `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --user-id analyst_01 `
    --session-id sess_xxxxxxxxxxxxxxxx

python -m green_direct.cli pilot-admin create-project `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --project-id project_1 `
    --name "试用项目 1" `
    --owner-user-id analyst_01

python -m green_direct.cli pilot-admin list-project-members `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --project-id project_1

python -m green_direct.cli pilot-admin grant-project-role `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --project-id project_1 `
    --user-id analyst_01 `
    --role analyst `
    --cannot-export-artifacts
```

`list-sessions` / `revoke-session` 用于服务器侧应急会话管理；撤销后对应 bearer-token 会话会立即失效，并写入 `UPDATE_USER` 审计。`create-project` 会把 `--owner-user-id` 指定用户设为项目创建人并授予项目 `admin`；若不指定 owner，则默认使用执行命令的平台管理员。`grant-project-role` 可用 `--can-export-artifacts` 或 `--cannot-export-artifacts` 明确维护导出权限；`disable-project-member` 可禁用单个项目成员关系；`archive-project` 可归档项目，归档后不能再新增或更新成员。

## 6. 启动服务

内网或反向代理后的推荐命令：

```powershell
$env:PYTHONPATH = "src"
$env:GREEN_DIRECT_ENABLE_PILOT_AUTH = "1"
$env:GREEN_DIRECT_PILOT_STORE_DIR = "D:\GreenDirectPilot\pilot_store"
$env:GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT = "0"

python -m streamlit run src/green_direct/ui/app.py `
    --server.address=127.0.0.1 `
    --server.port=8503 `
    --server.headless=true `
    --browser.gatherUsageStats=false
```

如果必须在内网网卡上直接监听，应通过防火墙、VPN 或网关限制访问来源。公网域名访问必须使用 HTTPS 反向代理，并继续保持应用侧登录门禁。

## 7. 备份

每天至少备份一次 `GREEN_DIRECT_PILOT_STORE_DIR`，并在重要试用前手动备份：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
    -File scripts\backup_pilot_store.ps1 `
    -StoreDir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    -BackupDir D:\GreenDirectPilot\backups
```

备份 ZIP 包含账号、项目、任务、结果索引、artifact metadata/payload 和审计日志。不要把备份提交到 Git。

## 8. 恢复

恢复前先停止 Streamlit 服务，并确认目标目录为空。恢复脚本不会覆盖非空目录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
    -File scripts\restore_pilot_store.ps1 `
    -BackupZip D:\GreenDirectPilot\backups\green-direct-pilot-store-20260616-093000.zip `
    -StoreDir D:\GreenDirectPilot\pilot_store_restored
```

恢复后可把 `GREEN_DIRECT_PILOT_STORE_DIR` 指向恢复目录做只读核查；确认无误后再切换正式服务目录。

## 9. 过期清理

Artifact payload 已支持保留策略。管理员可定期执行：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin purge-expired-artifacts `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin
```

清理只删除到期 payload，保留 `artifact.json` 和历史索引，并写入项目级 `DELETE_ARTIFACT` 审计。当前还没有原始上传文件清理和后台定时调度。

## 10. 任务卡死恢复

当前 `LocalJobStore` 已记录 `worker_id` 和 `last_heartbeat_at`，并已有第一条 worker 执行路径和最小轮询命令；但试用版还没有正式队列、进程守护、worker 级取消或自动重试。如果 Streamlit 进程中断、服务器重启或未来 worker 异常退出，可能留下长期 `running` 的任务元数据。管理员可先查看任务状态：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin list-jobs `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --status running `
    --stale-after-minutes 60
```

确认需要恢复后再执行：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin fail-stale-jobs `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --stale-after-minutes 60
```

该命令会把超过阈值未 heartbeat 的 running 任务标记为 `failed`，写入项目级 `COMPLETE_JOB` 审计，并保留原 `worker_id`、最后 heartbeat 和错误说明。它只修复任务元数据，不会终止操作系统进程，也不代表已经有正式后台队列、自动重试或资源回收。

平台管理员也可以在 Streamlit “平台管理 -> 任务运维”中查看超时运行任务，并点击“标记超时运行任务失败”。该入口复用同一服务层语义，适合 Render 单 Web Service 首次内测时不方便进入 Shell 的场景。

如果某个任务已经进入 `failed` 或 `canceled` 终态，且原始输入 artifact 仍存在、原始请求人仍有项目提交权限，平台管理员可以把它克隆为一个新的 queued job：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin retry-job `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --project-id project_1 `
    --study-id study_1 `
    --job-id job_failed `
    --new-job-id job_failed_retry_1
```

`retry-job` 会保留原任务的请求人、任务类型、输入 fingerprint 和 `input_artifact_ids`，并写入 `SUBMIT_JOB` 审计 metadata：`retry_of_job_id`、`retry_of_status` 和原始脱敏错误说明。它不会修改原任务，不会重试 queued/running/succeeded 任务，也不是自动重试策略；如需重试很多任务，应先排查失败原因和资源限制。

worker wrapper 可使用同一 CLI 认领 queued job：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin claim-next-job `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --worker-id pilot-worker-1 `
    --job-type technical_study `
    --job-type economic_study
```

该命令只把一个 matching queued job 标记为 `running`，写入 `worker_id` 和 heartbeat，不会执行技术仿真、经济性测算或导出任务。不要在真实队列中人工随手执行；如果没有 worker 随后接管计算，任务会停留在 `running`，需要再通过 stale cleanup 恢复。

如果 job 是通过 `queue_job_with_input_artifact()` 提交的 `technical_study` + `job_payload.task="hourly_detail"`，或 `economic_study` + `job_payload.task="annual_cashflow"`，可先用一次性 worker 命令演练完整闭环：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin run-worker-once `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --worker-id pilot-worker-1 `
    --job-type technical_study `
    --job-type economic_study
```

`run-worker-once` 会认领一个 matching queued job。对 `technical_study/hourly_detail`，它读取 `job_payload`、`technical_summary`、`config_snapshot` 和三条 `input_curve_*` artifact，补算单方案逐小时明细，写回 `ArtifactKind.HOURLY_DETAIL`；对 `economic_study/annual_cashflow`，它读取 `technical_summary`、`recommendation_inputs` 和经济 summary artifact，为所选方案写回电源侧/同一主体 `ArtifactKind.ANNUAL_CASHFLOW`。当前年度现金流 worker 仅支持固定价/网页组价经济性结果，逐时价格曲线结果需等价格曲线 artifact 化后再补；全量技术仿真、全量经济性测算、推荐、图表包或报告导出仍未后台化。

如果当前部署只有一个 Streamlit Web Service，平台管理员也可以在“平台管理 -> 任务运维”点击“处理一个排队任务”。该按钮复用与 `run-worker-once` 相同的受支持任务执行链路，但运行在当前 Web 进程内，只适合首次内测排障和小任务补算，不是自动守护进程。

完成管理员 bootstrap 后，也可以启动最小轮询 worker，让它持续认领受支持的 queued job：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin run-worker-loop `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --worker-id pilot-worker-1 `
    --job-type technical_study `
    --job-type economic_study `
    --poll-interval-seconds 5
```

`run-worker-loop` 会反复执行与 `run-worker-once` 相同的受支持任务。可用 `--max-jobs` 做有限批处理，用 `--idle-exit-after` 在连续空轮询后退出，便于 CI、脚本或一次性演练。Docker Compose 部署已提供可选 worker profile：先完成管理员初始化，再执行 `docker compose --profile worker up -d green-direct-worker`。当前本地 JSON store 仍不适合多 worker 并发写入；试用期建议最多启动一个 worker loop。

认领后，worker wrapper 可周期性刷新 heartbeat 和进度：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin heartbeat-job `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --worker-id pilot-worker-1 `
    --project-id project_1 `
    --study-id study_1 `
    --job-id job_1 `
    --current 2 `
    --total 5 `
    --message "running block 2/5"
```

该命令要求 `worker_id` 与任务已记录的 worker 一致，只刷新 running job 的 heartbeat/进度，不会标记任务成功或失败。

worker wrapper 完成任务后可标记终态：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin complete-worker-job `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --worker-id pilot-worker-1 `
    --project-id project_1 `
    --study-id study_1 `
    --job-id job_1

python -m green_direct.cli pilot-admin fail-worker-job `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --worker-id pilot-worker-1 `
    --project-id project_1 `
    --study-id study_1 `
    --job-id job_1 `
    --error-message "sanitized worker failure"
```

成功和失败都会写入项目级 `COMPLETE_JOB` 审计。失败信息必须是脱敏错误，不要包含原始曲线、服务器路径、token、密码或完整堆栈。

## 11. 审计日志抽查

管理员可在 Streamlit “平台管理 -> 审计日志”中只读抽查全局审计或指定项目审计，并按动作筛选。服务器 Shell 中也可用 CLI 抽查：

```powershell
$env:PYTHONPATH = "src"
python -m green_direct.cli pilot-admin list-audit-events `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --limit 20

python -m green_direct.cli pilot-admin list-audit-events `
    --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
    --actor-user-id admin `
    --project-id project_1 `
    --action download_artifact `
    --limit 20
```

不传 `--project-id` 时读取全局审计日志；传入 `--project-id` 时读取该项目的项目级审计日志。CLI 输出为 TSV，包含时间、动作、执行人、项目/研究/任务线索、目标对象和脱敏 metadata。当前 Web 页和 CLI 都是本地运维抽查入口，不替代正式审计后台、跨项目聚合搜索或集中日志平台。

## 12. 冒烟检查

每次上线或回滚后至少检查：
- 未登录用户只能看到登录页；
- 管理员可登录并看到“平台管理”，且能进入“审计日志”查看最近审计事件；
- 普通用户必须选择或创建项目后才进入六步工作流；
- Demo 技术仿真、经济性测算、方案推荐能跑通；
- 禁止导出的项目成员不能下载历史 artifact 或 06 页导出文件；
- `pilot-admin list-users`、`enable-user`、`list-sessions`、`revoke-session`、`list-projects`、`list-project-members`、`list-audit-events`、`list-jobs`、`claim-next-job`、`heartbeat-job`、`complete-worker-job`、`fail-worker-job`、`retry-job`、`run-worker-once`、`run-worker-loop`、`purge-expired-artifacts` 和 `fail-stale-jobs` 可执行；
- 新运行日志不包含明文密码、明文 token、原始曲线内容。

## 13. 回滚

回滚前先备份当前 store。代码回滚应优先切换到上一份已验证源码目录或上一提交，不要删除 pilot store。若新版本写入了旧版本不认识的 metadata，应先用恢复目录核查旧版本能否读取关键结果，再切换生产入口。

## 14. 仍未完成的生产化事项

- 正式队列、worker 级取消、自动重试策略和限流；当前仅有活动任务取消元数据、stale running 置失败运维入口、failed/canceled 任务手动克隆重试入口、按需 hourly detail / annual cashflow 的 queued job 入口，平台管理页手动处理一个排队任务 / 恢复超时 running 任务元数据，以及最小 `run-worker-loop` 轮询 worker；
- SQLite/Postgres 或对象存储适配；
- 原始上传文件保存、留存和清理；
- 完整历史结果恢复、跨项目搜索和报告版本管理；结果索引标记/置顶和软删除已有第一版；
- 目标服务器上的 HTTPS/反向代理实机演练、系统服务托管、监控告警和集中日志；
- CI/CD、版本化发布包和自动化端到端冒烟。
