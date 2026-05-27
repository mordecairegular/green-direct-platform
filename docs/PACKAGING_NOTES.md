# 打包说明

状态：当前打包入口说明
最近更新：2026-05-27

## 1. 当前有两个打包方向

本项目目前区分两个 Windows 使用入口。

| 入口 | 适用对象 | 包含能力 | 状态 |
|---|---|---|---|
| 完整 Streamlit 便携包 | 项目开发者或深度试用者 | 主界面、技术测算、经济性、推荐、图表原型 | 后续继续维护 |
| 独立方案遍历试用程序 | 快速发给同事试算 | 三条 CSV、容量遍历、方案概览 Excel、逐小时详表 ZIP | 当前优先可构建 |

独立方案遍历试用程序不是长期主产品形态，只是用于快速暴露数据、计算口径、容量范围和导出体验问题。

## 2. 独立方案遍历试用程序

构建命令：

```powershell
.\scripts\build_batch_trial_exe.ps1
```

构建入口：

```text
GreenDirectBatchTrial.spec
packaging\pyinstaller\run_batch_trial_tool.py
src\green_direct\ui\batch_trial_gui.py
```

构建产物：

```text
dist\GreenDirectBatchTrial\GreenDirectBatchTrial.exe
```

发给同事时复制整个文件夹：

```text
dist\GreenDirectBatchTrial\
```

不要只复制单个 exe。

配套说明：

- `docs/BATCH_TRIAL_TOOL_USER_GUIDE.md`
- `docs/BATCH_TRIAL_DISPATCH_AND_CALCULATION.md`

## 3. 完整 Streamlit 便携包

早期便携包策略是“便携包 + 内置 Python 虚拟环境”，用于启动完整 Streamlit 应用：

```text
绿电直连测算工具_便携版\
├─ 启动绿电直连测算工具.bat
├─ README_先看我.txt
├─ requirements.txt
├─ pyproject.toml
├─ src\
├─ config\
├─ samples\
├─ docs\
├─ outputs\
└─ .runtime\
```

该方向仍可保留，但当前未作为本次收口的主要构建目标。

## 4. 打包边界

打包产物不应改变计算口径。任何打包入口都必须调用仓库内同一套 `src/green_direct/` 技术计算、经济性和推荐模块。

如果后续新增正式桌面版或网页部署，应先更新本文档和 `notes/HANDOFF_FOR_NEW_MACHINE.md`。
