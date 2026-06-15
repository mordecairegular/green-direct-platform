# 内部试用部署 Runbook

本文面向 10-20 人内部试用，不等同于正式公网 SaaS。公网可访问时也只能按邀请制受控内测 Route A 推进：不开公开注册，不接 EMS、SCADA、调度自动化、真实电表或生产控制网络。

## 1. 部署边界

允许：
- 内网、VPN 或受控反向代理后的 Streamlit 服务；
- 管理员创建账号，试用用户登录后选择项目工作区；
- 项目级技术 summary、经济 summary、推荐 portfolio 和审计日志写入 `GREEN_DIRECT_PILOT_STORE_DIR`；
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

## 3. 环境变量

以 `.env.example` 为准，内部试用至少需要：

```powershell
$env:GREEN_DIRECT_ENABLE_PILOT_AUTH = "1"
$env:GREEN_DIRECT_PILOT_STORE_DIR = "D:\GreenDirectPilot\pilot_store"
$env:GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT = "0"
$env:GREEN_DIRECT_MAX_UPLOAD_MB = "20"
```

`START_GREEN_DIRECT_APP.bat` 和 `scripts/start_green_direct_app.ps1` 主要服务本地桌面体验。服务器或多人试用建议使用显式 Streamlit 命令，并确认 `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0`。

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

之后可在 Streamlit 的“平台管理”页创建试用账号、重置密码、停用用户、授予/撤销平台管理员，并维护项目成员和导出权限。应至少保留两个活跃平台管理员，避免单点锁死。

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

## 10. 冒烟检查

每次上线或回滚后至少检查：
- 未登录用户只能看到登录页；
- 管理员可登录并看到“平台管理”；
- 普通用户必须选择或创建项目后才进入六步工作流；
- Demo 技术仿真、经济性测算、方案推荐能跑通；
- 禁止导出的项目成员不能下载历史 artifact 或 06 页导出文件；
- `pilot-admin list-users` 和 `purge-expired-artifacts` 可执行；
- 新运行日志不包含明文密码、明文 token、原始曲线内容。

## 11. 回滚

回滚前先备份当前 store。代码回滚应优先切换到上一份已验证源码目录或上一提交，不要删除 pilot store。若新版本写入了旧版本不认识的 metadata，应先用恢复目录核查旧版本能否读取关键结果，再切换生产入口。

## 12. 仍未完成的生产化事项

- 正式后台 worker、排队、取消、重试和限流；
- SQLite/Postgres 或对象存储适配；
- 原始上传文件保存、留存和清理；
- 完整历史结果恢复、删除、标记和跨项目搜索；
- HTTPS/反向代理配置样例、系统服务托管、监控告警和集中日志；
- CI/CD、版本化发布包和自动化端到端冒烟。
