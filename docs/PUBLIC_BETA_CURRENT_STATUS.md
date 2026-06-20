# 公网内测当前状态单

日期：2026-06-17

用途：给项目负责人快速判断“现在能不能发给同事、能不能开始公网部署、下一步到底点什么”。长流程仍以 `docs/PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md` 和 `docs/PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md` 为准。

可用脚本生成实时状态：

```powershell
python scripts\report_public_beta_status.py --check-remote
python scripts\report_public_beta_status.py --check-remote --check-performance
```

该脚本只读；`--check-remote` 只执行 dry-run push 和远端门槛检查，不会真实推送。`--check-performance` 会额外运行一组代表性技术/经济性 benchmark 快照，用于判断大方案池性能是否有明显退化。

## 当前结论

本地试用包已经可以作为最快 fallback 发给同事；公网 Route A 的代码分支已经推送到 GitHub，用户已在 GitHub 网页人工确认仓库是 Private，GitHub Actions `Internal Pilot Quality Gate` 已通过最近一次部署工程化 checkpoint；后续文档小提交以 GitHub Actions 页面最新 run 为准。下一步是登录 Render，导入 Blueprint，然后接 Cloudflare 与电脑端移动网络验收。

## 已验证

- 当前分支：`codex/UI`；
- 当前最新提交以 `git log -1 --oneline` 为准；
- `python scripts\preflight_internal_pilot_deploy.py --summary`：预期 PASS；
- `git push --dry-run origin codex/UI`：通过，说明远端认证和分支推送路径可用；
- `python scripts\preflight_internal_pilot_deploy.py --require-git-sync --summary`：预期 PASS；
- GitHub 仓库 Private：2026-06-17 已由用户在 GitHub 网页人工确认；可用 `--github-private-manually-confirmed` 记录该人工确认；
- GitHub Actions：2026-06-17 已在 Chrome 中确认 `Internal Pilot Quality Gate #5` 对提交 `1b3af4d` completed successfully，耗时约 1m18s；
- 本地试用包：`release/GreenDirectLocalTrial_20260617.zip`，约 4.12 MB，具体构建提交见包内 `BUILD_INFO.txt`；
- 本地试用 ZIP 已确认不包含 `.venv`，首次启动会在线创建环境并安装依赖。
- 性能快照可通过 `python scripts\report_public_beta_status.py --check-performance` 一并输出；当前本机样本约为：168 小时、30 个方案、summary-first 技术仿真 0.18s 量级；5000 行经济性 summary + 保留 20 个年度现金流 0.83s 量级。该值用于本机趋势观察，不作为不同服务器的固定 SLA。

## 当前未完成

- 尚未在 Render 创建 Web Service；当前 Chrome 打开 Render Blueprint 页面时跳转到登录页 `https://dashboard.render.com/login?next=%2Fblueprints`，需要用户登录 Render 后继续；
- 尚未在 Cloudflare 配置 Access；
- 尚未完成电脑端移动网络验收。

## 最短下一步

如果继续公网 Route A：

1. 运行 `python scripts\report_public_beta_status.py --check-remote --check-performance --github-private-manually-confirmed`；
2. 或单独运行 `python scripts\preflight_internal_pilot_deploy.py --require-git-sync --summary`，预期 PASS；
3. 若本机已安装/登录 `gh`，运行 `python scripts\preflight_internal_pilot_deploy.py --require-github-private --summary` 自动核验 Private；
4. 若要用人工 Private 确认替代 `gh` 自动确认，运行 `python scripts\preflight_internal_pilot_deploy.py --require-github-private --github-private-manually-confirmed --summary`；
5. 用户在 Chrome 中登录 Render；
6. 按 `docs/PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md` 导入 Render Blueprint、初始化管理员、接 Cloudflare Access、做电脑端移动网络验收。

如果公网平台当天卡住：

1. 运行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_local_trial_package.ps1`；
2. 发送 `release/GreenDirectLocalTrial_20260617.zip` 给少量同事；
3. 明确告知这只是本地单机试用，不是公网多人网站。

如果同事电脑无法稳定访问 pip，可先运行 `scripts\prepare_local_trial_wheelhouse.ps1`，再用 `scripts\build_local_trial_package.ps1 -IncludeWheelhouse` 生成带依赖缓存的本地 ZIP。

## 不要跳过

- 不要把 GitHub 仓库设为 Public；
- 不要关闭 `GREEN_DIRECT_ENABLE_PILOT_AUTH`；
- 不要为了 Vercel / Cloudflare Pages 首发而重写当前 Streamlit 应用；
- 不要在未完成 Cloudflare Access 与应用内账号双门禁前把公网链接发给真实同事；
- 不要把本地 JSON store 多实例扩成正式生产架构。
