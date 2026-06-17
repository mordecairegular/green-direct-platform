# 公网内测当前状态单

日期：2026-06-17

用途：给项目负责人快速判断“现在能不能发给同事、能不能开始公网部署、下一步到底点什么”。长流程仍以 `docs/PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md` 和 `docs/PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md` 为准。

可用脚本生成实时状态：

```powershell
python scripts\report_public_beta_status.py --check-remote
```

该脚本只读；`--check-remote` 只执行 dry-run push 和远端门槛检查，不会真实推送。

## 当前结论

本地试用包已经可以作为最快 fallback 发给同事；公网 Route A 尚未真正上线，因为本地 `codex/UI` 分支还没有推送到 GitHub，且 GitHub 仓库 Private 状态仍需自动或人工确认。

## 已验证

- 当前分支：`codex/UI`；
- 当前最新提交以 `git log -1 --oneline` 为准；
- `python scripts\preflight_internal_pilot_deploy.py --summary`：预期 PASS；
- `git push --dry-run origin codex/UI`：通过，说明远端认证和分支推送路径可用；
- 本地试用包：`release/GreenDirectLocalTrial_20260617.zip`，约 4.12 MB，具体构建提交见包内 `BUILD_INFO.txt`；
- 本地试用 ZIP 已确认不包含 `.venv`，首次启动会在线创建环境并安装依赖。

## 当前未完成

- 尚未执行 `git push origin codex/UI`；
- `python scripts\preflight_internal_pilot_deploy.py --require-git-sync --summary` 会失败在 `git:sync`，这是未 push 的预期结果；
- 当前机器未安装 GitHub CLI `gh`，所以 `--require-github-private` 不能自动确认仓库 Private；
- 尚未在 Render 创建 Web Service；
- 尚未在 Cloudflare 配置 Access；
- 尚未完成手机 4G/5G 验收。

## 最短下一步

如果继续公网 Route A：

1. 用户确认允许推送；
2. 执行 `git push origin codex/UI`；
3. 推送后运行 `python scripts\report_public_beta_status.py --check-remote`，确认 git sync 和 GitHub Private 状态；
4. 或单独运行 `python scripts\preflight_internal_pilot_deploy.py --require-git-sync --summary`，预期 PASS；
5. 安装/登录 `gh` 后运行 `python scripts\preflight_internal_pilot_deploy.py --require-github-private --summary`，或在 GitHub 网页人工确认仓库是 Private；
6. 等 GitHub Actions `Internal Pilot Quality Gate` 通过；
7. 按 `docs/PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md` 导入 Render Blueprint、初始化管理员、接 Cloudflare Access、做手机验收。

如果公网平台当天卡住：

1. 运行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_local_trial_package.ps1`；
2. 发送 `release/GreenDirectLocalTrial_20260617.zip` 给少量同事；
3. 明确告知这只是本地单机试用，不是公网多人网站。

## 不要跳过

- 不要把 GitHub 仓库设为 Public；
- 不要关闭 `GREEN_DIRECT_ENABLE_PILOT_AUTH`；
- 不要为了 Vercel / Cloudflare Pages 首发而重写当前 Streamlit 应用；
- 不要在未完成 Cloudflare Access 与应用内账号双门禁前把公网链接发给真实同事；
- 不要把本地 JSON store 多实例扩成正式生产架构。
