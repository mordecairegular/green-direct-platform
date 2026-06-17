# 本地试用版分发说明

目标：让同事尽快在自己电脑上试用当前 Streamlit 网页版完整工作流，而不是退回旧的独立方案遍历小工具。

## 推荐分发方式

发送 `release/GreenDirectLocalTrial_YYYYMMDD.zip`。

重新生成当前日期本地试用包：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_local_trial_package.ps1
```

如需保留解压后的构建目录用于检查，可追加 `-KeepExpanded`。生成的 ZIP 位于 `release/`，该目录不进入 Git。

同事使用步骤：

1. 解压 ZIP 到本地目录；
2. 双击 `START_GREEN_DIRECT_LOCAL_TRIAL.bat`；
3. 首次运行会自动创建 `.venv` 并安装运行依赖，通常需要几分钟，网络较慢时可能需要 5-10 分钟；
4. 浏览器会自动打开本地地址，通常是 `http://localhost:8503`；
5. 使用期间不要关闭启动窗口。

如果电脑已经准备好 Python 环境，也可以双击 `START_GREEN_DIRECT_APP.bat` 直接启动。

本地试用包要求同事电脑已安装 Python 3.10 或更新版本；如果没有 Python 或首次运行网络无法安装依赖，需要另做离线包或免安装 EXE。如果首次安装中断，重新双击启动文件即可继续检查和补装依赖。

## 本次本地版保留什么

- 保留当前 Streamlit 网页界面和 01-06 六步工作流；
- 保留 Demo、曲线上传、方案仿真、经济性测算、推荐、图表和已有下载导出入口；
- 保留当前本地运行的操作逻辑，默认从 `8503` 到 `8515` 自动选择可用端口。

## 本次本地版不承诺什么

- 不包含公网多人登录和统一后台账号管理；
- 不包含 Cloudflare / Render / GitHub Actions 上线链路；
- 不把“正式报告导出”作为本次分发验收项；
- 不保证无 Python 的电脑可以直接运行；若需要完全免安装 EXE，需要另做 PyInstaller 打包和验证。

## 建议打包内容

- `START_GREEN_DIRECT_LOCAL_TRIAL.bat`、`START_GREEN_DIRECT_APP.bat`；
- `src/`、`scripts/start_green_direct_app.ps1`；
- `requirements-runtime.txt`、`requirements.txt`、`pyproject.toml`；
- `config/`、`samples/` 中的 CSV 模板；
- `README.md`、`docs/USER_QUICK_GUIDE.md`。

上述内容已由 `scripts/build_local_trial_package.ps1` 自动复制并压缩；不要手工拖拽文件打包，避免漏掉最新源码或启动脚本。

## 给同事的最短话术

```text
请解压后双击 START_GREEN_DIRECT_LOCAL_TRIAL.bat。第一次启动会安装依赖，通常需要几分钟，网络较慢时可能需要 5-10 分钟。浏览器打开后按 01-06 页顺序试用；如只想体验，可以先用 Demo。使用期间不要关闭黑色启动窗口。
```
