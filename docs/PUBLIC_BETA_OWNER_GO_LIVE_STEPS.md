# 公网内测负责人 30 分钟操作单

用途：给项目负责人执行“让同事用手机或移动网络访问”的最短上线动作。长说明见 `docs/PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md`，本文只保留必须按顺序完成的动作。

## 当前判断

当前项目不适合直接用 Vercel / Cloudflare Pages 作为主机。现阶段应用是 Streamlit 长进程，并依赖 `/data/pilot_store` 保存账号、项目、任务和结果。首轮公网内测推荐：

```text
GitHub 私有仓库
-> GitHub Actions 质量门
-> Render Docker Web Service + persistent disk
-> Cloudflare DNS / HTTPS / Access
-> 应用内账号登录
```

## 0. 开始前确认

在本地项目目录运行：

```powershell
python scripts\preflight_internal_pilot_deploy.py --summary
```

预期：`Deployment readiness: PASS`。

再运行：

```powershell
python scripts\preflight_internal_pilot_deploy.py --require-git-sync --summary
```

如果只提示 `git:sync`，说明本地提交还没推到 GitHub，这是正常的最后卡点。继续第 1 步。

仓库必须是 Private。若本机没有 GitHub CLI，可直接在 GitHub 仓库页面人工确认 visibility 为 Private。

## 1. 推送 GitHub

确认当前分支：

```powershell
git status --short --branch
```

推送内测分支：

```powershell
git push origin codex/UI
```

推送后复查：

```powershell
python scripts\preflight_internal_pilot_deploy.py --require-git-sync --summary
```

预期：PASS。

## 2. 等 GitHub Actions

打开 GitHub 仓库的 Actions 页面，等待 `Internal Pilot Quality Gate` 通过。

首次发布建议手动触发一次该 workflow，并勾选 `run_smoke`。

不要在质量门失败时继续 Render 部署。

## 3. Render 导入仓库

在 Render 选择 Blueprint / Import Git Repository，导入同一个 GitHub 私有仓库。

核对：

- 服务名：`green-direct-internal-pilot`
- Runtime：Docker
- 分支：`codex/UI`
- Health check：`/_stcore/health`
- Auto deploy：checks pass
- Instances：`1`
- Persistent disk：`green-direct-pilot-store`
- Disk mount：`/data`
- Disk size：至少 `10GB`

关键环境变量应由 `render.yaml` 自动带入：

- `GREEN_DIRECT_ENABLE_PILOT_AUTH=1`
- `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0`
- `GREEN_DIRECT_PILOT_STORE_DIR=/data/pilot_store`
- `GREEN_DIRECT_MAX_UPLOAD_MB=20`
- `GREEN_DIRECT_MAX_SCENARIOS_PER_RUN=20000`
- `GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS=1`

部署完成后先打开 Render 默认域名。预期看到应用登录页，而不是直接进入工作流。

## 4. 初始化管理员

在 Render Web Service Shell 运行：

```bash
python -m green_direct.cli pilot-admin doctor \
  --store-dir /data/pilot_store \
  --json
```

只有 `status=pass` 才继续。

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

登录后立刻修改管理员密码。

## 5. 创建首批账号

先只创建小范围账号：

- 1 个备用平台管理员；
- 1 个可导出测试账号；
- 1 个不可导出测试账号；
- 3-5 个真实同事账号。

每个真实同事都应加入一个项目，并按需要设置是否允许下载/导出。

## 6. 做首次备份和恢复演练

在 Render Shell 先做一次临时备份恢复验证：

```bash
tar -C /data -czf /tmp/green-direct-pilot-store-first-launch.tgz pilot_store
rm -rf /tmp/pilot_store_restore_check
mkdir -p /tmp/pilot_store_restore_check
tar -C /tmp/pilot_store_restore_check -xzf /tmp/green-direct-pilot-store-first-launch.tgz
python -m green_direct.cli pilot-admin doctor \
  --store-dir /tmp/pilot_store_restore_check/pilot_store \
  --json
```

预期：恢复目录 doctor 返回 `status=pass`。真实备份文件应保存到 Git 仓库外的受控位置。

## 7. 接入 Cloudflare

在 Cloudflare 中：

- 给 Render 服务添加自定义域名；
- 配置 DNS CNAME；
- 开启 HTTPS；
- 在 Zero Trust Access 创建 self-hosted application；
- 只允许内测邮箱或邮箱域访问。

Cloudflare Access 是第一层门禁，应用内账号是第二层门禁，两层都保留。

## 8. 手机验收

用手机 4G/5G 网络验证：

- 非白名单邮箱不能通过 Cloudflare Access；
- 白名单邮箱通过后仍需应用账号登录；
- 未登录不能进入六步工作流；
- 普通用户看不到其他人的项目；
- 可导出用户能下载结果；
- 不可导出用户不能下载结果；
- 创建项目、跑 Demo、重启服务后项目仍存在；
- 审计日志能看到登录、项目和下载动作。

这些都通过后，再把链接发给真实同事。

## 9. 不能为了快而跳过的事

- 不要把 GitHub 仓库设为 Public；
- 不要关闭 `GREEN_DIRECT_ENABLE_PILOT_AUTH`；
- 不要开放公开注册；
- 不要让同事上传高度敏感或正式生产数据；
- 不要把当前系统当成 EMS / SCADA / 调度控制系统；
- 不要在未 benchmark 前把并行进程数调高；
- 不要同时启动多个共享本地 JSON store 的独立 worker。

## 10. 如果当天公网平台卡住

可以先发送本地试用包：

```text
release/GreenDirectLocalTrial_20260617.zip
```

本地包保留当前网页操作逻辑，但不是公网多人试用，不替代以上上线流程。
