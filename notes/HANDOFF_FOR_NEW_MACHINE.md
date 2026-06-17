# 换电脑与 AI 协作交接说明

日期：2026-05-22  
用途：在更换电脑、切换 Codex / Claude Code、丢失历史聊天或重新开始会话时，帮助 AI 无感接续本项目。

## 1. 核心原则

本项目应把重要上下文沉淀在项目文件夹内，而不是依赖某一次聊天记录。

原因：

- 项目文件夹在移动硬盘中，代码和文档可以方便切换电脑；
- Codex / Claude Code 的历史聊天不一定随项目文件夹迁移；
- 新电脑、新客户端或新会话可能完全不知道此前讨论；
- 因此，项目规则、产品决策、架构方向、计算口径和下一步计划必须写进仓库文档。

一句话：

```text
让项目文件夹自己成为长期记忆体。
```

## 2. 换电脑后第一句提示词

在新电脑、新会话、新 AI 工具中，建议第一句直接发送：

```text
请先不要改代码。请阅读 AGENTS.md、CLAUDE.md、notes/HANDOFF_FOR_NEW_MACHINE.md、notes/PRODUCT_POLISH_LOG.md、docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md，以及 notes/architecture_reframe_20260519/ 下的所有文档。读完后请用简短中文总结：当前项目定位、V0.1 基线、最新架构方向、下一步建议，并说明你后续开发时会如何维护 PRODUCT_POLISH_LOG.md 和 HANDOFF_FOR_NEW_MACHINE.md。之后再等我给具体任务。
```

如果本次任务会修改现有风光储核心计算逻辑，再追加：

```text
本次可能涉及核心计算，请额外阅读 ALGORITHM_SPEC.md、TEST_CASES.md、OUTPUT_SCHEMA.md，并在修改后运行 pytest。
```

如果本次任务会开发柴发、经济性或推荐引擎，再追加：

```text
本次可能涉及柴发、经济性排序或推荐引擎，请重点阅读 notes/architecture_reframe_20260519/04_HOURLY_DISPATCH_LOGIC_WITH_DIESEL.md 和 02_TARGET_ARCHITECTURE_AND_CALCULATION_LOGIC.md。不要把柴发混入电网下网，不要让经济性评价反向污染技术调度。
```

如果本次任务会开发经济性评价模块，还必须追加：

```text
经济性评价 V1 口径已于 2026-05-21 确认，并于 2026-05-22 更新储能更换与 FIRR 求解口径。请先阅读 docs/ECONOMY_RECOMMENDATION_V1_MAP.md、docs/references/economic_evaluation/00_README_使用说明.md 和 docs/references/economic_evaluation/经济性评价V1计算口径_合并版.md。V1 是不考虑贷款的年度项目投资现金流模型，Year 0 建设、默认运营期 25 年，运行成本无进项税，储能更换进项税保留；储能更换取循环寿命和默认 15 年日历寿命先到者，换后重新开始计算；FIRR 不使用折现率，且多次变号时应先判断是否只有唯一稳定 IRR 根；经济性评价不得修改技术调度结果。注意同一主体 `net_avoided_grid_cost_price` 与负荷侧 `load_side_avoided_charge_price` 是两个不同价格口径，不要混用。
```

如果本次任务会继续开发图表或推荐展示，还建议追加：

```text
图表模块已于 2026-05-21 开始重构为“方案图谱”：系统代表方案 + 用户加入方案 + 方案总览/能量流向/运行时序/经济性分析。请先阅读 notes/PRODUCT_POLISH_LOG.md 中“图表模块重构：对标参考图的第一版方案图谱”。当前图表只读取技术结果和经济性 V1，不得反向修改调度结果。碳排放和经济敏感性暂未确认口径，不要凭空生成。
```

如果本次任务涉及恢复旧文档或旧打包产物，请注意：2026-05-21 已做项目清理，清理前检查点为 `535ee78 Checkpoint before repository cleanup`。旧图表模块讨论稿、历史 `outputs/` 导出样例、`build/`、`dist/`、`release/` 等已从工作区移除；必要时从该提交恢复。

如果本次任务涉及追溯早期 AI 构建提示词、V0.1 验收记录或旧状态快照，请到 `archive/20260522_historical_build_materials/` 查看。该目录是历史归档，不是当前活跃开发入口。

### 2.1 内部试用 / 受控公网内测上线前 Claude Code 提示词

如果目标是 10-20 人内部试用上线，或从内网 pilot 升级到邀请制受控公网内测 Route A，请优先使用 `docs/CLAUDE_CODE_INTERNAL_PILOT_PROMPTS.md`。

该文档把 Claude Code 任务拆成六类可复制提示词：
- 上下文读取；
- 上线前 review/debug；
- 方案遍历与经济性测算性能专项；
- Streamlit UI 提升（先 UI 审查与切片选择，再做小切片落地）；
- 后台账户、Job 和 `ResultStore` 架构设计；
- 托管平台公网测试演练。

不要把 review/debug、性能专项和 UI 提升合并到同一轮。前者用于清 P0/P1 风险，性能专项用于量化并推进大方案池等待时间问题，UI 提升用于改善六步工作流体验；三者的判断标准不同，混在一起容易漏掉上线风险。

受控公网内测 Route A 不是正式公网 SaaS：应关闭开放注册，用户由管理员创建或邀请；软件不得接入 EMS、SCADA、调度自动化、真实电力设备或生产控制网络；公网访问前必须补独立导出权限、上传文件安全、项目/Run/Artifact 留存、审计日志、HTTPS/反向代理、备份恢复和回滚说明。

对应审计和性能文档：

- `docs/PUBLIC_BETA_DEPLOYMENT_AUDIT.md`：把受控公网内测准备方案映射为当前仓库的 P0 审计矩阵；
- `docs/PUBLIC_BETA_CURRENT_STATUS.md`：给项目负责人查看当前是否已能 push、是否仍缺 GitHub Private 确认、是否可以先发本地包 fallback 的短状态单；
- `docs/PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md`：把首次受控公网内测发布串成执行作战单，覆盖本地 preflight、push、GitHub Actions、Render Blueprint、Web Service Shell doctor/bootstrap、Cloudflare Access、手机验收和回滚；
- `docs/PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md`：给非程序员负责人使用的 30 分钟短操作单，按 preflight、push、GitHub Actions、Render、管理员 bootstrap、账号、备份恢复、Cloudflare Access 和手机验收顺序执行；
- `docs/PUBLIC_BETA_FEEDBACK_TRIAGE.md`：首轮 10-20 人内测反馈模板、P0/P1/P2 分级、管理员排查顺序、脱敏 `support-bundle`、只读 CLI 排查命令和反馈表字段；
- `docs/MANAGED_PUBLIC_BETA_DEPLOYMENT.md`：记录托管平台公网测试路线，推荐容器/PaaS 承载应用本体、Cloudflare 做 DNS/HTTPS/Access；
- `docs/MOBILE_NETWORK_TRIAL_CHECKLIST.md`：面向“同事用手机/移动网络试用”的最短操作清单；
- `docs/PERFORMANCE_OPTIMIZATION_PLAN.md`：记录方案遍历、summary-first、并行、经济性批量化和后台 Job 的性能路线；
- `docs/INTERNAL_PILOT_ARCHITECTURE_PLAN.md`：记录内部 10-20 人 pilot 后台账户、项目、Job、ResultStore、Render 单实例边界和未来 SQLite/Postgres + 对象存储/worker 演进路线；
- `README_DEPLOY.md` 和 `SECURITY.md`：记录 Docker/compose 内测部署、安全边界、反向代理、备份恢复和已知限制；
- `scripts/benchmark_internal_pilot_performance.py`：用于记录技术仿真和经济性测算的可重复 benchmark；经济性真实等待优先看 `--no-tracemalloc` 直计时，默认模式用于同时观察 Python heap 峰值；`--economy-retain-cashflow-count N` 可模拟当前 UI “全量计算 summary、只为少量方案保留年度现金流”的策略。
- `scripts/report_public_beta_status.py`：用于生成只读公网 Route A 状态报告；默认只看本地状态，`--check-remote` 会执行 `git push --dry-run`、`--require-git-sync` 和 `--require-github-private` 检查，但不会真实 push；`--check-performance` 会额外运行一组代表性技术/经济性 benchmark 快照；
- `scripts/preflight_internal_pilot_deploy.py`：用于推送 GitHub/Render 前检查部署文件、安全默认值、Compose/Render Web 与 worker 关键环境变量、Render 持久盘配置、`.dockerignore`、Git tracked 推送源安全（私有 `.env`、本地运行状态、数据库/日志/压缩包、超大文件）、可选 Streamlit smoke，可选 `--pilot-store-dir` 运行 store doctor，可选 `--require-git-sync` 确认当前分支、upstream 与 `render.yaml` 部署分支一致并已推到 upstream，以及可选 `--require-github-private` 通过 GitHub CLI 确认部署源仓库 visibility 为 Private。
- `scripts/preflight_internal_pilot_deploy.py --summary`：面向人类操作的发布就绪摘要，只显示通过/失败总览、失败项和下一步建议；`--json` 仍用于 CI、归档和 agent 读取。
- `scripts/smoke_streamlit_app.py`：用于推送 GitHub/Render 前做本地服务器口径冒烟检查，默认启用 pilot auth、关闭 runtime snapshot、使用临时 pilot store 并检查 `/_stcore/health`。
- `.github/workflows/internal-pilot-quality.yml`：GitHub 推送/PR 质量门，自动运行 compile、部署 preflight、临时目录版 pilot store doctor 和全量 pytest；手动触发并勾选 `run_smoke` 时会额外启动 Streamlit 做健康检查。
- `render.yaml`：当前 pilot Blueprint 显式部署 `codex/UI`，设置 `numInstances=1` 和 `autoDeployTrigger: checksPass`；Render 应等 GitHub Actions 质量门通过后再自动部署，避免部署默认分支或未通过检查的提交。
- `docs/CLAUDE_CODE_INTERNAL_PILOT_PROMPTS.md`：UI 提升提示词已明确要求先做当前运行截图/浏览器审查，再选择一个可验收小切片；首轮 UI 提升优先考虑窄屏/手机可用性或 03 经济性首屏节奏，不要让 Claude Code 一次性“美化全部六页”。

2026-06-17 当前部署前事实状态：
- 最新性能/部署状态 checkpoint 主题包括 `chore(deploy): add performance status snapshot`、`chore(release): support wheelhouse local trial installs` 和 `chore(perf): benchmark retained economy cashflows`；前一经济性性能 checkpoint 提交主题为 `perf(economy): trim summary hot path`；上一批量方案性能 checkpoint 提交主题为 `perf(batch): stream scenario generation`；此前连续部署/性能 checkpoint 包括 `807fb1b chore(deploy): require private github source`、`428fcfa chore(deploy): align browser path defaults`、`86b9319 chore(deploy): check runtime dependency sync`、`d6e8cb6 chore(deploy): verify render pilot disk`、`805f601 chore(deploy): require pilot backup materials`、`d6c33d4 perf(core): inline bess summary accumulation`、`fd8ca63 perf(core): reduce bess summary dispatch calls`、`511c0d4 perf(core): skip bess hour case in summaries`、`725f465 chore(deploy): lock pilot runtime env checks`、`68d43f8 docs(pilot): sharpen claudecode launch prompts`、`345f3a9 perf(economy): fast path temporary replacement irr dips` 和 `b28d4c5 perf(core): skip redundant bess output clamps`；
- `python -m pytest -q` 最近一次全量结果为 `417 passed`；
- `python -m pytest tests\test_bess_dispatch.py tests\test_single_scenario.py tests\test_batch_runner.py -q` 最近一次针对 BESS summary-only hot path 结果为 `68 passed`；
- 最近一次 BESS summary-only profile 小切片把 48 个 8760 小时含储能方案、summary-only、无常驻明细的 cProfile 函数调用数约从 2,112,037 降到 430,117，cProfile 总耗时约从 0.753s 降到 0.430s；该优化只减少 `max()` / `min()` 和最大功率维护的 Python 调用，不改变 V0.1 dispatch 口径；
- 随后一轮把有储能 summary-only 路径内联为 `_run_bess_summary_only()` 累加器，同参数 cProfile 函数调用数约从 430,117 降到 9,733，直接计时约从 0.34s 到 0.20s，带 `tracemalloc` benchmark 约从 15.7857s 到 4.0213s；完整逐小时明细路径仍调用 `dispatch_bess_hour_values_with_limits()`。后续若改 BESS 调度口径，必须同步更新完整明细路径、summary-only 累加器和一致性测试；
- 最新经济性性能 checkpoint 把 FIRR 多根 fallback 的候选利率扫描改为 NumPy 批量 NPV 与符号穿越区间识别；候选利率列表、唯一根/多根判定和最终 bisection 语义不变。5,000 行 synthetic economic summary、`retain_annual_cashflows=False` 的 `run_economic_study()` 直接计时约从 18.3s 降到 1.0s，cProfile 函数调用数约从 56,606,020 降到 4,366,020；
- `python scripts\preflight_internal_pilot_deploy.py --run-smoke --json` 已通过，`failed_count=0`，包含 `smoke:streamlit`；
- `python scripts\preflight_internal_pilot_deploy.py --pilot-store-dir .runtime\preflight_doctor_smoke --json` 已通过，`failed_count=0`，包含 `pilot-store:*` 检查；
- `python scripts\preflight_internal_pilot_deploy.py --json` 已通过，`failed_count=0`；当前静态 preflight 包含 Docker/Compose/Render Web 与 worker 关键环境变量、`git-tracked:*` 推送源安全检查，已确认 tracked file count=330，未发现私有 `.env`、本地运行状态、pickle/database/log/压缩包或超过 95 MiB 的文件；
- 首次发布作战单已新增 bootstrap 后备份/恢复演练：Render Shell 走临时 tar 包恢复到空目录并运行 `pilot-admin doctor`，自有 Windows/本地环境走 `scripts/backup_pilot_store.ps1` 和 `scripts/restore_pilot_store.ps1`；`preflight_internal_pilot_deploy.py` 已把内部部署 runbook 与备份/恢复脚本纳入 REQUIRED_FILES，移动网络验收清单也要求备份保存到 Git 仓库外受控位置且恢复目录 doctor 通过；
- Render Blueprint 静态门槛已锁定 persistent disk 名称 `green-direct-pilot-store`、挂载路径 `/data` 和容量至少 10GB；`preflight_internal_pilot_deploy.py --json` 会输出 `render:disk-name` 与 `render:disk-size` 检查；
- Docker/Render runtime 依赖同步已纳入 preflight：`runtime-deps:pyproject-sync` 会校验 `requirements-runtime.txt` 与 `pyproject.toml` 的 `[project].dependencies` 一致；Dockerfile 检查也锁定运行镜像通过 `requirements-runtime.txt` 安装依赖；
- Docker/Compose/Render 的 Chromium/Kaleido browser path 已对齐为 `BROWSER_PATH=/usr/bin/chromium`；部署 preflight 会检查 Dockerfile、Compose Web、Compose worker 和 Render Web 环境变量，降低图表 PNG 导出在不同部署入口下行为不一致的风险；
- 02 页默认并行技术仿真进程数已改为部署可调：`GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS` 默认 1，并被 Dockerfile、docker-compose、Render、`.env.example` 和 preflight 锁定。小 benchmark 显示 105 个 168 小时方案 summary-first 时 1 进程约 0.338s、2 进程约 1.1925s，因此默认保持 1，目标服务器若调到 2-4 必须先跑真实大样本 benchmark；
- 批量技术仿真已改为流式消费方案池：`iter_scenarios()` 按原顺序逐个生成 `Scenario`，`run_batch()` 使用 `estimated_scenario_count` 做 total/warning/scenario_count，串行和并行 chunk 都不再先物化完整 `Scenario` list；benchmark 脚本也改为 `count_scenarios()` + `islice(iter_scenarios(...))`，避免测试工具自己先展开完整方案池。该优化只减少方案池对象生成和 chunk 调度压力，不改变 V0.1 技术调度、summary 字段、经济性或推荐口径；
- 流式方案迭代最近验证：`python -m pytest tests\test_batch_runner.py -q` 通过 18 项；`python -m pytest tests\test_study_runner.py tests\test_ui_import.py::test_technical_workload_estimate_scales_with_detail_retention_and_workers tests\test_ui_import.py::test_scenario_count_limit_notice_blocks_oversized_pool -q` 通过 14 项；`compileall` 通过；105 个 168 小时方案 summary-first、1 worker 约 0.3494s / 峰值 Python heap 约 1.25MB，2 worker 约 1.3318s / 1.546MB；572 个 8760 小时方案 summary-first、0 个明细保留、1 worker 带 `tracemalloc` 约 38.8425s / 2.625MB；新增 `--no-tracemalloc` 后，同参数直计时约 1.86-1.95s；
- 经济性 summary-only 热路径最近继续瘦身：summary 数字字段缺失值判断走快速路径，IRR 现金流符号扫描合并为一次遍历，benchmark 脚本新增 `--economy-only-summary-rows` 经济性单独压测入口。5,000 行 synthetic economic summary、固定价、双经济视角、`retain_annual_cashflows=False` 的 direct timing 约从 0.8741s 降到 0.7352s；随后 benchmark 脚本新增 `--no-tracemalloc`，本机 5,000 行经济性 summary-only 直计时约 `0.8115s`，默认 heap 跟踪口径应只用于观察内存和相对趋势；最新 benchmark 又新增 `--economy-retain-cashflow-count N`，同样 5,000 行样本下不保留年度现金流约 `0.7366s`，保留电源侧/同一主体各 20 个年度现金流约 `0.7986s`，说明“只保留少量现金流”的额外成本较小；这些优化不改变电源侧 V1、同一主体税前模型、FIRR 多根判断或推荐排序；
- 部署 preflight 新增 `--summary` 摘要模式，方便非程序员和下一位 agent 快速判断上线卡点；当前未推送状态下，`--require-git-sync --summary` 应提示 `git:sync` 失败并建议同步 `codex/UI` 到 GitHub；
- GitHub 私有仓库核验已纳入可选 preflight：`--require-github-private` 会读取 `remote.origin.url` 并通过 `gh repo view` 确认 visibility 为 `PRIVATE`；当前机器未安装 `gh` 时，可在 GitHub 页面人工确认仓库为 Private 后加 `--github-private-manually-confirmed` 重跑。2026-06-17 用户已确认仓库为 Private；
- GitHub Actions 已在 Chrome 中确认：`Internal Pilot Quality Gate #5` 对提交 `1b3af4d` completed successfully，耗时约 1m18s；前几个失败 run 是状态报告测试要求 CI 存在 ignored 本地 ZIP，已由 `test(deploy): allow missing local trial zip in ci` 修复；
- Render 尚未创建服务；Chrome 打开 `https://dashboard.render.com/blueprints` 会跳到 Render 登录页，需要用户登录 Render 后继续导入 Blueprint；
- `docs/CLAUDE_CODE_INTERNAL_PILOT_PROMPTS.md` 已同步到最新 checkpoint：交接摘要包含本地试用包 wheelhouse、只读公网状态脚本、`--check-performance` 性能快照、流式方案迭代、经济性 summary-only 热路径和少量年度现金流保留 benchmark 边界，并补充 UI 审查时不得为了截图关闭 pilot auth、不得为 Vercel 首发重写前端、不得绕过项目/成员/导出权限和审计服务层；本地 ahead 数量应以接手时 `git status --short --branch` 为准；
- `python -m pytest tests\test_deployment_artifacts.py -q` 已通过，12 项通过，覆盖首次发布作战单、Render 分支、GitHub Actions 质量门、GitHub 私有仓库可选检查、默认并行进程数部署变量和部署 preflight；
- `python scripts\preflight_internal_pilot_deploy.py --require-git-sync --summary` 最近一次按预期失败，唯一失败项是 `git:sync`：本地 `codex/UI` 仍领先 `origin/codex/UI` 且未 push；具体 ahead/behind 数量以接手时 `git status --short --branch` 和该 preflight 输出为准。该命令现在还会核对当前分支和 upstream 是否匹配 `render.yaml` 的部署分支；部署前应重新运行该命令获取实时状态；
- `python scripts\preflight_internal_pilot_deploy.py --require-github-private --summary` 最近一次失败原因是本机缺少 GitHub CLI `gh`；这不是代码或部署配置失败。首次公网内测前应安装/登录 `gh` 后重跑，或在 GitHub 网页人工确认 `https://github.com/mordecairegular/green-direct-platform` 是 Private；
- `git push --dry-run origin codex/UI` 最近一次通过，说明远端认证和分支推送路径可用，但尚未真正 push；`docs/PUBLIC_BETA_CURRENT_STATUS.md` 已记录当前公网 Route A 的完成项、未完成项和最短下一步；
- 当前 `origin` 为 `https://github.com/mordecairegular/green-direct-platform.git`；
- 用户在等待过久后已明确接受“上线或本地分发都可以”，并要求本地程序分发尽可能保留当前网页操作逻辑和界面逻辑，报告导出不需要打包，欢迎页也不是阻塞项；如果继续做本地分发，不要优先重写成独立桌面 GUI，除非用户明确要求。
- 本轮新增本地试用分发路线：`START_GREEN_DIRECT_LOCAL_TRIAL.bat` 会创建 `.venv`、安装运行依赖并调用现有 Streamlit 启动器；`LOCAL_TRIAL_README.md`、`docs/USER_QUICK_GUIDE.md` 和 `docs/LOCAL_TRIAL_DISTRIBUTION.md` 记录给同事的启动说明与边界；
- 已新增可重复本地试用包构建脚本：`scripts/build_local_trial_package.ps1` 会复制当前 `src/`、启动脚本、运行依赖、配置、示例 CSV 和用户说明，生成 `release/GreenDirectLocalTrial_YYYYMMDD.zip`；`release/` 位于 ignored 目录下，不进入 Git checkpoint；包内不包含 `.venv`、公网账号后台、Render/Cloudflare 链路或正式报告导出；
- 弱网/无法访问 pip 的同事可走 wheelhouse 路线：先运行 `scripts/prepare_local_trial_wheelhouse.ps1` 下载当前 Windows/Python ABI 的依赖 wheel，再运行 `scripts/build_local_trial_package.ps1 -IncludeWheelhouse` 生成带 `wheelhouse/` 的 ZIP；启动器会优先用 `--no-index --find-links wheelhouse` 安装依赖。该路线仍要求同事电脑已安装 Python，不是免安装 EXE；
- 已生成本地试用 ZIP：`release/GreenDirectLocalTrial_20260617.zip`。如果当前源码已有新 checkpoint，先重新运行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_local_trial_package.ps1`，不要直接发送旧 ZIP；
- `START_GREEN_DIRECT_LOCAL_TRIAL.bat` 已修正首次运行时 `.venv` 创建分支的 delayed expansion 问题；在新生成的分发目录运行 `START_GREEN_DIRECT_LOCAL_TRIAL.bat -CheckOnly` 已通过，确认本地启动链路可用且不启动长进程。首次在线安装依赖可能需要 5-10 分钟；若中断，重新双击会继续检查和补装依赖。此前尝试 PyInstaller `GreenDirectTool` 超时，已停止并清理 `build/GreenDirectTool` 与 `dist/GreenDirectTool` 半成品；
- 因此当前最快交付路径是先发送本地试用 ZIP 给同事；公网 Route A 仍是第二条线，需经用户确认后推送当前分支到私有 GitHub，等待 GitHub Actions 质量门通过，再按 Render/Cloudflare checklist 做真实部署演练；
- 公网 Route A 的非程序员负责人短操作单已补充为 `docs/PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md`，并纳入 `preflight_internal_pilot_deploy.py --summary` 的通过提示和 REQUIRED_FILES。当前静态 preflight 通过后会提示先运行 `--require-git-sync --summary`、`--require-github-private --summary`，再按短操作单执行。
- 技术仿真批量热路径继续做了一个微切片：`PreparedCurveData` 缓存 `load_power_sum`、`pv_positive_pu_sum`、`wind_positive_pu_sum`，summary-only 路径用这些批量共享统计计算总负荷电量和新能源可发电量，避免每方案重复扫描同一曲线。该切片不改变风光负值站用电、BESS SOC、summary 字段或推荐排序；单次 benchmark 未观察到显著加速，价值主要是减少重复工作并让后续 hot path 更清晰。
- 公网内测排障新增脱敏 support bundle：`build_pilot_support_bundle()`、`pilot-admin support-bundle` 和 Streamlit `平台管理 -> 审计日志 -> 脱敏排查包` 会聚合账号/项目/成员/任务/result/artifact/audit 元数据与 doctor 摘要，要求平台管理员执行，可按项目输出 JSON；它不读取 artifact payload，不输出登录名、显示名、项目名、artifact storage URI、result label、audit metadata value 或绝对 store 路径。后续让 Claude Code / Codex review/debug 时，优先让管理员生成该 bundle，而不是让用户贴原始曲线、完整 artifact payload 或未脱敏日志。

若用户提出 Vercel、Cloudflare Pages/Workers 等成熟平台，请先区分平台角色：当前 Streamlit 长进程 + pilot store 形态不适合直接部署到 serverless/edge runtime；短期公网内测推荐 Render/Fly/Railway/Cloud Run 等容器服务托管应用本体，Cloudflare 负责域名、HTTPS 和 Access 门禁。若要改架构，优先把本地 store 换成数据库/对象存储和后台 worker，再考虑前端重写。

## 3. 当前项目定位

本项目已经从：

```text
绿电直连风光储多方案批量测算工具
```

升级规划为：

```text
绿电直连 / 微电网项目方案策划与推荐平台
```

旧 V0.1 风光储技术测算模块仍然是重要基线，但不再是最终产品边界。

新的目标流程：

```text
项目输入
-> 输入审查
-> 候选方案生成
-> 逐小时技术仿真
-> 政策合规筛选
-> 轻量经济性排序
-> 代表方案推荐
-> 图表、报告、导出
```

## 4. 当前重要文档

### 4.1 当前有效 AI 开发规则

- `AGENTS.md`
- `CLAUDE.md`
- `notes/HANDOFF_FOR_NEW_MACHINE.md`

### 4.2 架构重定向材料

- `notes/architecture_reframe_20260519/01_EXPERT_REVIEW_BRIEF.md`
- `notes/architecture_reframe_20260519/02_TARGET_ARCHITECTURE_AND_CALCULATION_LOGIC.md`
- `notes/architecture_reframe_20260519/03_MIGRATION_AND_POLISH_PLAN.md`
- `notes/architecture_reframe_20260519/04_HOURLY_DISPATCH_LOGIC_WITH_DIESEL.md`

### 4.3 当前接口和产品打磨记录

- `docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`
- `docs/ECONOMY_RECOMMENDATION_V1_MAP.md`
- `docs/WEB_APP_WORKFLOW_AND_UI_RESTRUCTURE.md`
- `notes/PRODUCT_POLISH_LOG.md`

### 4.4 V0.1 技术基线

- `PRD.md`
- `ALGORITHM_SPEC.md`
- `DATA_SCHEMA.md`
- `OUTPUT_SCHEMA.md`
- `TEST_CASES.md`
- `UI_SPEC.md`
- `ECONOMY_EXTENSION_SPEC.md`

这些旧文档不删除，但应理解为 V0.1 基线，不是未来产品边界。

### 4.5 历史归档资料

- `archive/20260522_historical_build_materials/`

该目录保存早期 AI 构建提示词、历史验收记录、旧状态快照和已完成任务说明。后续开发默认不读取该目录，只有追溯历史时再看。

## 5. 当前代码基线

当前已有能力包括：

- CSV 数据读取和编码识别；
- 8760 / 8784 小时支持；
- 负荷、光伏、风电曲线校验；
- 光伏 / 风电负值按站用电处理；
- 风光储容量组合枚举；
- 单方案逐小时能量平衡；
- 储能 SOC 滚动；
- 储能功率、容量、效率约束；
- 上网比例政策约束；
- 与电网交换功率限制；
- 批量测算；
- 汇总 Excel 和逐小时 CSV / ZIP 导出；
- 六模块 Streamlit 工程工作台第一版（推荐与图表已拆页）；
- 经济性评价 V1、同一主体税前测算和推荐方案 V1；
- 下网电价曲线 V1，可选 CSV / Excel 上传，且只能使用当前会话明确上传的曲线；
- 图表模块、HTML 图表包和 Word 友好 PNG 图表包；
- 启动器、端口自检、本地单机结果快照恢复和会话隔离的后台 PNG 生成；
- 可选内部试用登录门禁、项目工作区门禁和最小平台账号/项目成员管理页；
- 本地 pilot backend 服务骨架：`LocalPilotAuth`、`LocalPilotRegistry`、`LocalPilotAdminService`、`PilotAccessService`、`LocalJobStore`、`LocalResultStore`；
- pytest 测试基线。

最近一次上线前交接检查，已验证：

```text
python -m pytest -q
287 passed
python -m compileall -q src scripts tests
```

## 6. 后续开发优先方向

建议顺序：

1. 结构化输入诊断；
2. `StudyResult` 和 `HourlyEnergyLedger` 骨架；
3. 推荐引擎和 `RecommendationPortfolio`；
4. 轻量经济性排序；
5. 柴发资产和离网 / 备用调度策略；
6. 项目级 Job 状态页、ResultStore 结果接入、hourly artifact 和跨会话按需明细；
7. UI 和报告围绕推荐方案重塑。

当前特别说明：

- 现有图表模块效果不理想，可以视为可替换原型，不需要优先保护；
- 后续不要把主要精力放在继续打磨现有图表模块；
- 应先把逐小时计算、风光储规模配置逻辑、轻量经济性排序、方案筛选与推荐逻辑搞清楚并实现；
- 等计算和推荐结果稳定后，再重新设计图表和报告展示。

不建议一开始就：

- 大规模重构所有目录；
- 直接重写核心算法；
- 直接做完整 NPV / IRR / 税费 / 融资模型；
- 草率加入柴发给储能充电；
- 把推荐逻辑写死在 Streamlit UI 中。

## 7. 每次开发后的文档维护规则

后续无论使用 Codex 还是 Claude Code，每次出现以下情况，都应更新文档。

### 7.1 必须更新 PRODUCT_POLISH_LOG.md 的情况

当发生以下任何一种情况：

- 用户提出新的产品判断；
- 用户否定或调整之前的方向；
- 形成新的计算口径；
- 形成新的 UI / 工作流判断；
- 形成新的经济性、柴发、推荐策略判断；
- 解决一个关键体验或计算问题；
- 专家提出被采纳或暂缓的建议。

更新方式：

```text
在 notes/PRODUCT_POLISH_LOG.md 末尾新增日期小节，
记录问题、讨论结论、状态、原因和经验。
```

### 7.2 必须更新 HANDOFF_FOR_NEW_MACHINE.md 的情况

当发生以下任何一种情况：

- 项目定位发生变化；
- 推荐的下一步开发顺序变化；
- 新增关键架构文档；
- 新增必须阅读的文档；
- 运行方式或测试命令变化；
- 重要模块落地，例如推荐引擎、柴发、经济性；
- 换电脑后第一句提示词需要调整。

更新方式：

```text
保持本文档简洁可读，
只记录换电脑和新 AI 会话继续开发所需的最新事实。
```

### 7.3 必须更新 AGENTS.md / CLAUDE.md 的情况

当发生以下任何一种情况：

- 对后续 AI 开发的规则发生变化；
- 允许或禁止某类改动；
- 核心架构方向变化；
- 必读文档列表变化；
- 新增必须遵守的算法边界。

### 7.4 必须更新架构文档的情况

当发生以下任何一种情况：

- 柴发调度策略确定；
- 储能是否允许柴发 / 电网充电确定；
- 经济性排序字段确定；
- 推荐方案类别确定；
- `HourlyEnergyLedger` 字段确定；
- `StudyResult`、`RecommendationPortfolio` 等对象实现或调整。

对应目录：

```text
notes/architecture_reframe_20260519/
```

## 8. 换电脑后环境检查

进入项目目录后建议先执行：

```powershell
git status --short
python -m pytest
```

如果依赖缺失：

```powershell
python -m pip install -r requirements.txt
```

运行 Streamlit 优先使用统一启动器：

```powershell
.\START_GREEN_DIRECT_APP.bat
```

或使用 PowerShell 启动脚本，它会先做导入自检，并默认从 8503 到 8515 选择空闲端口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_green_direct_app.ps1
```

如果只检查环境：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_green_direct_app.ps1 -CheckOnly
```

构建独立方案遍历试用程序：

```powershell
.\scripts\build_batch_trial_exe.ps1
```

构建后试用入口位于：

```text
dist\GreenDirectBatchTrial\GreenDirectBatchTrial.exe
```

该入口只包含方案遍历、方案概览 Excel 和逐小时方案详表 ZIP 导出，不包含完整 Streamlit、图表、经济性评价和推荐引擎。发给同事时复制整个 `dist\GreenDirectBatchTrial\` 文件夹。

## 9. Git 建议

虽然项目在移动硬盘上可以直接切换电脑，但仍建议使用 git 记录关键状态。

每次完成一轮重要文档或代码改动后：

```powershell
git status --short
git add AGENTS.md CLAUDE.md README.md ROADMAP.md notes docs archive src tests
git commit -m "Update planning and architecture handoff docs"
```

如果不想马上提交，至少在切换电脑前查看：

```powershell
git status --short
```

确认哪些文件是未提交改动，避免换电脑后忘记当前状态。

## 10. 新 AI 会话的工作要求

新的 Codex / Claude Code 会话应遵守：

- 开始前先读本文档和 `AGENTS.md` / `CLAUDE.md`；
- 不要假设自己记得历史聊天；
- 不要把旧 V0.1 文档当成未来边界；
- 不要删除旧测试和旧文档；
- 不要把经济性评价混入技术调度；
- 不要把柴发输出混入电网下网；
- 推荐方案应有解释理由；
- UI 主界面不要默认展示全量枚举表、逐小时大表或经济性年度明细大表；这些应作为高级展开或下载项；
- 图表后续应围绕推荐方案和用户加入对比方案，而不是围绕全量枚举结果；
- 每次形成重要产品判断后更新 `PRODUCT_POLISH_LOG.md`；
- 每次影响跨电脑接续的信息后更新本文档。

## 11. 当前交接摘要

截至 2026-06-12：

- 已完成 V0.1 风光储技术测算基线；
- 已形成图表模块初步能力；
- 已分析对标软件，并确认目标是方案策划与推荐平台；
- 已同意经济性排序应提前进入推荐逻辑；
- 已确认经济性评价 V1 口径：不考虑贷款，Year 0 建设，默认运营期 25 年，输出年度现金流详表、FNPV、FIRR、静态回收期和动态回收期；2026-05-22 已更新为储能更换取循环寿命和默认 15 年日历寿命先到者，换后重新开始计算；
- 已实现经济性评价 V1 初版：`EconomicParams`、年度现金流计算、批量经济性汇总、轻量 Streamlit 试用入口和 11 个经济性测试；
- 已确认候选方案池必须有绿电来源：批量生成层跳过 `pv_capacity <= 0` 且 `wind_capacity <= 0` 的组合，不再枚举无新能源无储能或仅储能方案；
- 已根据浏览器批注做一轮低风险 UI 收纳：隐藏大表和明细、统一中文字段名、只保留 CSV/Excel 下载入口；
- 已将 `docs/references/economic_evaluation/` 精简为 README、V1 合并口径和官方来源清单三类文件；
- 已同意柴发应进入方案逻辑，尤其用于离网和备用场景；
- 已明确现有图表模块效果不理想，可在后续重构中替换或丢弃，不作为近期重点；
- 已更新 `AGENTS.md` 和 `CLAUDE.md`；
- 已新增架构重定向专家审查材料；
- 已新增每小时风光储网柴调度核心逻辑草案；
- 已将早期 AI 构建提示词、V0.1 验收记录和旧状态快照降级归档到 `archive/20260522_historical_build_materials/`，当前活跃开发不再把这些资料作为入口；
- 推荐引擎讨论已确认：默认推荐组合不要求用户先选择投资主体结构，应同时展示多视角方案；当前经济性 V1 更接近不同主体下的电源侧投资收益模型；同一主体全局增量收益和负荷侧收益先预留，后续补口径；
- 第一版推荐组合默认优先级已改为：同一主体 FIRR 最优、电源侧 FIRR 最优、负荷侧可成交收益最优、工程代表方案。工程代表方案从政策达标最小投资、高绿电占比、高自发自用、低弃电中选一个，默认低弃电；负荷侧席位需先满足电源侧最低可接受 FIRR 约束，再按负荷侧年度综合用能收益排序；
- 电源侧投资收益最佳方案默认以 FIRR 作为主排序指标：在政策达标候选集内，先筛 FIRR 可可靠计算，主排 FIRR 从高到低，辅助排序依次为静态回收期更短、动态回收期更短、FNPV 更高。已确认“自发自用电价”正式重命名为“绿电结算价”，计算字段统一使用 `green_power_settlement_price_with_vat`；当前代码中的 `self_use_price_with_vat` 只能作为迁移期旧字段。推荐 V1 应支持 8760 / 8784 逐小时绿电结算价、上网电价和电网购电价格曲线，后续再支持 15min；
- 经济性 V1 已补充独立的送出线路工程投资字段。该费用与其他固定资产投资都发生在 Year 0，但送出线路是绿电直连必需项，不能长期归入其他固定资产投资；第一版直接输入“送出线路工程投资总额（万元，含税）”。Year 0 全部初始投资中可抵扣增值税的部分统一按 10% 建设投资进项税率计；年度现金流中送出线路按 20 年直线折旧，并在经济性汇总中保留 `dedicated_connection_line_investment_with_vat`；
- 经济性 V1 折旧口径已澄清：Year 0 初始投资按 20 年、残值 0、直线法折旧；运营期发生的新增可折旧投资从次年到运营期最后一年线性折旧，残值 0。储能更换已按该口径新增 `bess_replacement_depreciation`；
- 当前不建议在方案遍历技术仿真中引入光伏逐年衰减；后续可在经济性 V2 或高级参数中增加年度电量衰减修正。若未来允许风电、光伏运营期不同，必须同步定义多年技术电量变化，不要只改现金流年限；
- 已新增底层输入原则：能在 CSV/Excel 中更清晰处理的数据准备、参数推导或清洗逻辑，不要强行塞入网页 UI；新增 UI 控件前要先判断是否更适合模板输入；
- 已新增推荐引擎 V1 计算口径草案：`docs/references/recommendation_engine/推荐引擎V1计算口径草案.md`。已确认价格曲线模板采用 CSV/Excel 上传，不做网页逐项录入；环境价值作为固定单价高级选项，默认 0，不做时间曲线；所有推荐席位默认只在政策达标候选集中排序；
- 2026-05-25 已补充并实现同一主体税前 FIRR 第一版：`docs/references/recommendation_engine/同一主体购电节费与税前FIRR口径.md`、`src/green_direct/economy/electricity_saving.py`、`src/green_direct/economy/single_entity_evaluator.py`、`tests/test_single_entity_economy.py`。同一主体合并口径不使用绿电结算价计算项目整体收益；默认按 `net_avoided_grid_cost_price` 计算自发自用购电节费，需要复核时可按电费清单组价：电能量/市场购电价格、上网环节线损费用、系统运行费用、输配电价、政府性基金及附加。V1 主排序采用税前 FIRR，不默认计算所得税。原电源侧 `evaluate_scenario_economy()` 未改，继续作为电源侧投资收益近似模型；
- 2026-05-25 已接入同一主体税前经济性 UI 试算和下载闭环：技术方案汇总 Excel 保持纯技术指标；电源侧经济性和同一主体税前经济性在经济性区域分别展示、分别下载汇总表，并支持所选方案 Year 0-Year N 年度现金流 Excel。经济性逐年明细是正式软件的可审计输出能力，不是临时复核包；后续其他经济性视角也应提供相应明细导出；
- 2026-05-25 已纠偏经济性参数分组：通用参数不得放进某一个推荐视角的高级参数区；储能更换投资比例、储能更换进项税率是通用经济参数，电池日历寿命放入储能参数区并说明当前只影响经济性更换、不参与小时调度；用户侧电费拆分字段必须尽量对应电费清单，避免使用“可节省/不可节省”等抽象命名；
- 2026-05-26 已增强同一主体年度现金流下载：工作簿包含 `方案说明`、`年度现金流`、`字段说明` 三张表。年度现金流表头带序号，字段说明表解释计算关系和口径差异；方案说明表展示风光储规模、主要政策指标、电量指标和同一主体关键经济性指标。后续电源侧、负荷侧年度详表也应沿用“方案上下文 + 编号表头 + 字段说明”的可复核结构；
- 2026-05-27 已再次纠偏经济性入口：固定价参数默认展示，不再通过“启用同一主体”开关才显示；价格曲线才是高级参数，后续用 CSV/Excel 上传。经济性参数区按 `基本参数`、`成本费用`、`收入和税金` 和 `电费构成参数` 分组；Year 0 建设投资、送出线路、其他固定资产和建设投资进项税率属于 `基本参数`，运营期运维和储能更换属于 `成本费用`，储能更换需说明按日历寿命和循环寿命先到者触发。`绿电结算价` UI 说明需强调其非用户到户电价，不含输配电价、政府基金及附加、系统运行费和容需量电费等；经济性测算按钮一次计算当前已实现的电源侧和同一主体视角；
- `其他经营收入` 属于 `收入和税金`，但一般项目没有，应放在高级折叠区默认隐藏，不占用主输入界面；
- 2026-05-27 已修正 `外部购电净成本单价` 组价公式：该参数不是原外部购网电全部电量类费用，而是 `原外部购网电电量类成本单价 - 绿电直连自发自用仍需缴纳费用单价`。若自发自用绿电仍缴输配电价和政府性基金及附加，这两项不能算作节省。1192 号文系统运行费暂按下网电量缴纳，自发自用绿电不作为“绿电仍缴系统运行费用”扣减；代码已新增 `green_direct_retained_*` 字段并在组价模式中扣减；
- 2026-05-27 已确认负荷侧默认席位改为 `负荷侧可成交收益最优`：新增基础参数 `电源侧最低可接受 FIRR`，默认 7%，字段建议 `min_power_side_acceptable_firr`。本席位先筛政策达标、负荷侧收益为正、电源侧 FIRR 可可靠计算且不低于最低可接受 FIRR，再按负荷侧年度综合用能收益排序。若用户清空最低 FIRR，则不对本席位排序并提示缺少可成交性约束。V1 暂不反算绿电结算价，只在用户给定价格条件下排序；
- 2026-05-27 已实现推荐方案 V1 试用并补齐四个默认席位：`同一主体 FIRR 最优`、`电源侧 FIRR 最优`、`负荷侧可成交收益最优` 和可切换的 `工程代表方案`。页面经济性区域下方新增 `推荐方案 V1（试用）`；完成经济性评价后应同时构造四个席位，同一方案命中多个席位时合并标签，不应静默漏掉同一主体或电源侧 FIRR 席位。合并标签时必须同时保留各席位贡献的关键指标，不能出现命中负荷侧席位但负荷侧收益字段缺失的推荐表。推荐组合 Excel 包含推荐组合、电源侧经济性汇总、同一主体经济性汇总和负荷侧可成交收益明细；
- 2026-05-28 已新增经济性评价与推荐 V1 导览文档 `docs/ECONOMY_RECOMMENDATION_V1_MAP.md`，用于给第一次接触项目的人说明参数、含义、代码入口、推荐席位和计算方式；
- 2026-06-04 已接入价格曲线 V1：`src/green_direct/economy/price_curves.py` 支持 CSV / Excel 读取、中文字段映射、8760 / 8784 校验、时间戳 / hour_index / 行序对齐和逐方案年度金额聚合；`run_economic_study()` 可选接收 `price_curve` 与 `hourly_details`，曲线模式只影响经济性和推荐排序，不改变技术调度。价格曲线 V1 只作为下网购电账单原始组分曲线，推荐模板为 `samples/price_curve_template_down_grid.csv`，文档副本为 `docs/templates/price_curves/price_curve_template_down_grid.csv`，字段包括 `timestamp`、`hour_index`、电度/市场购电价、线损费、系统运行费、输配电价、政府性基金及附加，以及当前不参与计算的 `month`、`peak_valley` 辅助列；绿电结算价、上网电价、度电环境价值、增值税率、负荷侧可减少费用和同一主体税前净节费不放入模板，继续由网页固定参数或内部公式得到。政府性基金及附加按不含税处理，其他下网电价组分按含税处理；计算方法审阅文档见 `docs/PRICE_CURVE_ECONOMY_CALCULATION_METHOD.md`。UI 口径：电价曲线在“方案仿真”页作为可选项目级输入上传，只有当前会话明确上传后才保存到 `project_price_curve_data` / `project_price_curve_meta` 并供“经济性测算”页使用；`.runtime/latest_session_snapshot.pkl` 不恢复旧价格曲线，用户只上传负荷、光伏、风电三条技术曲线时不得沿用历史电价。已有当前上传曲线时置灰外部购电净成本固定输入、电费清单组价开关和负荷侧单独覆盖。更换曲线或重跑技术仿真会清空旧经济性/推荐结果；测试见 `tests/test_price_curves.py`、`tests/test_study_runner.py` 和 `tests/test_ui_import.py`；
- 2026-05-28 已调整推荐默认口径：工程代表方案默认改为 `政策达标最小投资`；同一主体席位保留 FIRR 默认视角，并支持切换为 `同一主体动态回收期最短`；固定价模式默认减少用户输入，由外部购电净成本口径内部派生负荷侧筛选价，需要精确区分时再使用高级覆盖或电费清单组价；
- 2026-06-01 已在 Streamlit 继续落地工作流：`欢迎页`、`方案仿真`、`经济性测算`、`方案推荐及图表概览`、`图表下载和报告生成`。保留旧页面名到新页面名的兼容映射，避免旧会话状态导致页面进入异常；方案仿真页不再继续渲染经济性和图表；经济性测算页计算成功后保存 `recommendation_v1_inputs`；推荐图表页集中展示推荐组合和图表分析；下载报告页集中导出方案汇总、逐小时明细、图表 HTML ZIP、技术+经济汇总和简版 Markdown 报告；
- 2026-06-02 已把 Streamlit UI 深度改造成工程软件工作台第一版：左侧深蓝固定导航，顶部轻量项目状态条，主区按模块组织。方案仿真页把曲线数据、候选方案池、政策约束和专业参数放在主工作区；经济性测算页保留完整参数但分层收纳；推荐页先展示代表方案卡片和图表概览；所有下载按钮集中到“图表下载和报告生成”页。按钮跳转继续使用 `_workflow_page_target` pending 状态，仿真和经济计算完成后用 `st.rerun()` 刷新顶部状态条；推荐图表页已优先消费正式 `RecommendationPortfolio`，下载页图表 HTML ZIP 的多方案对比范围收窄为“推荐组合 + 当前报告方案”；Demo 候选范围为 27 个小方案，浏览器验证显示 15 个达标方案，未再出现 `workflow_page` widget key 报错；
- 2026-06-03 已把静态推荐样板页映射进一步接入正式 Streamlit 推荐图表页：`docs/ui/recommendation_dashboard_sample.html` 仍只作为视觉参考，mock 数据只允许留在 `docs/ui/`；正式推荐页卡片读取 `RecommendationPortfolio` 和技术/经济真实字段，新增排序标识、上网比例、无候选/待排序状态区分；顶部状态条从 `hourly_details.timestamp` 推导数据时间范围；推荐页底部新增下载报告入口和状态提示，默认报告方案优先取推荐组合有效 `scenario_id`，真实 CSV/Excel/HTML ZIP/Markdown 下载仍集中到“图表下载和报告生成”页；浏览器验证已走通欢迎页、Demo 仿真、经济性测算、推荐页、运行时序典型日和下载页；
- 2026-05-28 已新增第一层服务抽象 `src/green_direct/services/study_runner.py`：`run_economic_study()` 统一执行电源侧和同一主体经济性，`build_recommendation_study()` 统一构造推荐组合，`RecommendationInputSnapshot` 保存推荐所需的价格和门槛输入；
- 2026-06-04 已继续抽出技术研究服务入口：`TechnicalStudyInput`、`TechnicalStudyResult`、`StudyResult` 和 `run_technical_study()` 已落地；Streamlit 方案仿真页的 Demo 和正式测算不再直接调用 `read_curve_set()` / `run_batch()`，而是触发服务层。当前 UI 仍兼容写入 `batch_result`，同时新增 `study_result` 作为后续迁移入口；
- 2026-06-04 已把 Streamlit 主工作流调整为六模块：`欢迎页`、`方案仿真`、`经济性测算`、`方案推荐`、`图表概览`、`图表下载和报告生成`。旧 `方案推荐及图表概览` 会话状态映射到 `方案推荐`；02 页曲线卡 hover 显示负荷年总用电量、光伏/风电年利用小时；侧栏折叠态保留 48px 深蓝工具轨；Sankey 文字样式仅做展示层修正，不改变能源流向计算；
- 2026-06-01 已把四季典型日从固定月份中位日改为季节中心日法：按春 3-5 月、夏 6-8 月、秋 9-11 月、冬 12/1/2 月的完整 24 小时日期，使用负荷、风光、储能、电网、弃电、SOC 等逐小时字段标准化后选离季节平均曲线最近的真实日期；图表标题和说明标注 `MM/DD`；
- 2026-06-09 已在交付中心新增 Word 友好 PNG 图表包：HTML ZIP 继续用于 Plotly 交互复核，PNG ZIP 用于插入 docx。PNG 包复用同一图表清单并输出 `chart_manifest.csv`；默认 A4 纵向 Word 正文 16 cm 插入宽度、1800px 画布宽。静态 PNG 导出需要 `plotly>=6.1`、`kaleido>=1.0` 和可用 Chrome / Chromium；若环境缺失，HTML ZIP 不受影响，PNG 失败原因会写入 UI / warnings；
- 2026-06-09 已修复 Streamlit 启动入口与端口冲突问题：优先使用 `START_GREEN_DIRECT_APP.bat` 或 `scripts/start_green_direct_app.ps1` 启动；统一启动器会先做导入自检，默认从 8503 到 8515 选择空闲端口，并且只停止可确认属于本项目的旧 Streamlit 进程。不要再使用硬编码 8501 或裸 `streamlit run app.py` 的入口；若需要只检查环境，可运行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_green_direct_app.ps1 -CheckOnly`；
- 2026-06-10 已完成清理 C 盘后的 Streamlit 前端兼容排查：当前项目依赖应保持 `streamlit>=1.57,<1.58`、`plotly>=6.1`、`kaleido>=1.0`；启动器和 PyInstaller 入口会把 `TEMP/TMP/TMPDIR` 指向项目 `.runtime/tmp`，并自动设置 `BROWSER_PATH` 到本机 Chrome/Edge。若旧浏览器标签继续出现 `Failed to fetch dynamically imported module`，先强制刷新或重开 `http://localhost:8503`，因为正确的 `Metric`、`PlotlyChart`、`axios` 分块已验证可返回 JavaScript；PNG ZIP 已在当前 `.venv` 安装 `kaleido==1.3.0` 后验证可生成。
- 2026-06-10 已新增 Streamlit 重启后的本地结果恢复机制；2026-06-15 已按内部多人试用要求加安全边界：默认直接 `streamlit run src/green_direct/ui/app.py` 不保存、不恢复 `.runtime/latest_session_snapshot.pkl`，只有本地启动器 / PyInstaller 入口显式设置 `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=1` 时才启用。多人部署、内网服务器、容器或反向代理环境不得开启该变量；长期仍应实现正式 `ResultStore`；`.runtime/` 已加入 `.gitignore`。
- 2026-06-10 已修正图表网页端和 ZIP 导出一致性：新增共享能源色板 `src/green_direct/visualization/style.py`，网页 24H 运行策略图和 HTML/PNG 导出复用同一构图；PNG/HTML 图表包补充五类关键运行日和全年 8760/8784 曲线；季节典型日文件名不再嵌入日期，真实选中日期写入 meta。后续改图表颜色或 24H 运行图时优先改共享色板和 `build_operation_day_figure()`，不要单独给 PNG 另起一套样式。
- 2026-06-10 PNG ZIP 已改为后台生成；2026-06-15 已加多人试用安全修正：后台任务 key 包含 Streamlit 会话 ID，PNG ZIP 签名包含 `summary`、所选方案 `hourly_detail` 和对比方案表的数据指纹，新技术仿真会清空旧 PNG 导出缓存，快照也不再持久化 PNG ZIP 二进制。06 页提交后台线程任务，用户可切换页面，返回后自动收割结果；底层优先用 Plotly `write_images()` 批量渲染，失败再逐张回退。经济参数页默认风电造价 5000、光伏造价 2800，常调单位造价和运维单价使用 Streamlit 原生 `number_input` 内置步进微调，步长按字段内部定义（单位造价 100、运维 1），不要再用自定义按钮修改 `session_state` 后强制整页 rerun。顶部重复状态条已停止渲染，保留侧栏导航/状态和页面标题。PNG 图表包区域使用局部刷新显示运行中/完成/失败状态。S09 图中净交换显式按 `grid_export_power - grid_import_power` 展示，S10 全年曲线分为供需/上网弃电/SOC 三行，S02 政策阈值使用水平阈值线。
- 2026-06-15 已开始经济性测算性能优化：批量经济评价去除 `iterrows()`，年度折现因子按年限和折现率缓存，NPV 改用等价 Horner 形式，同一主体批量评价减少重复参数校验；常规单符号变化现金流的 IRR 直接走二分快路径，多符号变化仍走原候选率扫描和多根判断。该优化不改变年度现金流、FNPV、FIRR、回收期或推荐排序口径；后续仍需继续做 DataFrame/NumPy 批量化、后台 Job 和 `ResultStore`。
- 2026-06-16 已继续优化经济性 summary-only：`evaluate_batch_economy()` 和 `evaluate_batch_single_entity_pre_tax_economy()` 在 `retain_annual_cashflows=False` 且方案不在 `annual_cashflow_scenario_ids` 中时，不再构造完整年度现金流 `DataFrame`，只用现金流数组计算 FNPV、FIRR 和回收期；被指定保留的方案仍生成完整年度现金流表。小样本 220 个方案、168 小时、2 worker、技术 summary-first 后经济性 summary-only 从约 3.1503s 降至约 0.8120s；不改变经济性 V1 现金流口径或推荐排序口径。
- 2026-06-16 已把经济性 summary-first 接到 Streamlit 03 页和部署参数：默认 `GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD=1000`、`GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT=20`，超过阈值时 UI 调用 `run_economic_study(..., retain_annual_cashflows=False, annual_cashflow_scenario_ids=(...))`，仍全量计算经济性 summary、FIRR/NPV 和推荐排序，但只常驻前 N 个方案年度现金流；06 页会解释未常驻现金流的方案为什么没有年度现金流下载按钮。Dockerfile、docker-compose、render.yaml、`.env.example`、部署 README、runbook、安全说明、性能路线和审计矩阵已同步。后续仍需补逐时价格曲线现金流按需补算和正式队列。
- 2026-06-16 已新增固定价/网页组价经济性结果的按需年度现金流后台 Job：`RecommendationInputSnapshot` 和 `recommendation_inputs.json` 新增 `avoided_grid_params`（旧 artifact 缺字段时按 `load_side_avoided_charge_price` 兼容）；`persist_annual_cashflow_artifact()` 会写单方案 `ArtifactKind.ANNUAL_CASHFLOW` ZIP，并以 `power:<scenario_id>` / `single_entity:<scenario_id>` 挂回既有经济结果 record；`pilot_worker` 支持 `economic_study` + `job_payload.task="annual_cashflow"`，读取 `technical_summary`、`recommendation_inputs` 和可选 `power_economy_summary`，拒绝 `price_mode=hourly_curve`，为所选方案生成电源侧/同一主体年度现金流。06 导出页缺现金流时可提交后台任务、轮询并加载完成 artifact；docker-compose worker profile 已同时轮询 `technical_study` 和 `economic_study`。这仍不是全量经济性后台化、正式队列、价格曲线 cashflow 补算或 worker 级取消。
- 2026-06-16 已继续减少经济性批量评价固定开销：`OtherOperatingRevenueItem.is_active()` 不再为 `specific_years` 每次构造临时 set；新增 `_other_revenue_schedule()` 缓存其他经营收入年度表；电源侧 `evaluate_scenario_economy()` 将同一方案内每年不变的上网/自用收入、VAT 拆分、O&M 和基础折旧移出年度循环；随后新增 `_PowerEconomyContext` 和 `_SingleEntityEconomyContext`，让批量入口复用折现因子、固定资产拆分、其他收入年度表和默认电价口径。本轮 189 个方案、168 小时 benchmark 中 economy summary-only 约从 0.7345s 降到 0.6019s。该优化不改变经济性 V1 现金流字段或口径；后续继续推进 DataFrame/NumPy 批量化、后台 Job 和 `ResultStore`。
- 2026-06-16 已继续优化经济性 summary-only 年度循环固定开销：电源侧和同一主体 evaluator 在不保留年度现金流时不再为每年构造完整 row dict，只追加 year/net cashflow 到现金流数组；批量入口对未保留方案复用内部空年度现金流表哨兵，公开单方案调用仍保持独立空表语义。Profiler 样本从 189286 calls / 0.086s 降到 123514 calls / 0.044s；同一 benchmark 189 个方案 economy summary-only 本机样本约从 0.7749s 降到 0.5605s。该优化不改变年度现金流保留路径、FNPV/FIRR/回收期或推荐排序口径。
- 2026-06-16 已继续优化技术仿真 retained-hourly 固定开销：`run_single_scenario()` 新增 `collect_diagnostics` 开关，公开单方案默认保留 diagnostics，`run_batch()` hot path 显式关闭逐方案 diagnostics 构造；保留逐小时明细时，tiny float / `-0.0` 清零从 pandas DataFrame 后处理前移到 DataFrame 构造前的 numpy 数组处理，减少 pandas `mask/_where` 开销。189 个方案、168 小时、保留 20 个明细的 profile 样本从约 1,837,448 calls / 0.661s 降到约 1,493,928 calls / 0.517s；带 `tracemalloc` benchmark 速度受负载波动，但峰值 Python heap 从同参数前序样本约 2.47 MB 降到约 1.55 MB。该优化不改变 V0.1 dispatch、hourly ledger 字段或 summary 口径。
- 2026-06-16 已给本地 JSON store 补原子写入和协作文件锁第一版：`write_json()` 现在先写同目录临时文件、flush/fsync 后再 `replace()` 目标文件；如果替换失败，旧 JSON 保持不变并清理临时文件。随后新增 `local_store_lock()`，并把 `LocalPilotRegistry` 的账号/项目/成员写入、`LocalJobStore` 的提交/认领/进度/终态/stale cleanup、`LocalResultStore` 的 artifact/result/audit 写入纳入锁保护；多进程同时认领同一 queued job 的测试已覆盖只有一个 winner。该能力降低半写损坏和本地多进程读改写竞争风险，但仍不是数据库事务、冲突合并、正式队列或长期并发存储，10-20 人试用继续建议评估 SQLite/Postgres。
- 2026-06-17 已新增 pilot store 运行时自检入口：`src/green_direct/services/pilot_store_doctor.py` 提供 `run_pilot_store_doctor()`，`pilot-admin doctor --store-dir <dir> --json` 可在首个管理员 bootstrap 前后检查 store 目录可用性、JSON 原子写入/读取、payload 写入、协作文件锁、既有 metadata JSON 和审计 JSONL。Render persistent disk 挂载后、备份恢复后、创建管理员前应先运行；返回 `status=fail` 时不要继续 bootstrap 或启动 worker。该检查不替代数据库健康检查、备份校验或监控告警。
- 2026-06-16 已给历史结果索引补软删除第一版：`StudyResultRecord` 新增 `deleted_at` / `deleted_by_user_id`，`LocalResultStore.soft_delete_result_record()` 会隐藏结果索引但不删除 artifact payload，默认 `list_project_result_records()` / `list_study_result_records()` 不返回已删除记录；`PilotAccessService.delete_result_record()` 仅允许项目 admin 执行并写 `DELETE_RESULT_RECORD` 审计。Streamlit 欢迎页历史结果产物区已显示项目 admin 的“隐藏历史结果索引”入口。该能力不是完整历史结果页、报告版本标记、物理文件清除或数据库级回收站。
- 2026-06-16 已给历史结果索引补标记/置顶第一版：`StudyResultRecord` 新增 `pinned_at` / `pinned_by_user_id` / `label`，默认结果列表置顶优先、再按创建时间倒序；`LocalResultStore.mark_result_record()` 可标记或取消标记，`PilotAccessService.mark_result_record()` 仅允许项目 admin 执行并写 `UPDATE_RESULT_RECORD` 审计。Streamlit 欢迎页历史结果产物区已显示项目 admin 的“标记为重点结果”和备注输入。该能力不是正式报告版本管理、审批流或完整历史结果页。
- 2026-06-15 已新增内部试用后台模型骨架，并于 2026-06-16 补任务输入 artifact 引用契约和 payload 入队闭环：`src/green_direct/models/pilot_backend.py` 定义 `User`、`Project`、`ProjectMembership`、`ProjectStudy`、`Job`、`JobArtifact`、`StudyResultRecord`、`AuditLog` 及角色/任务/产物状态枚举；`Job.input_artifact_ids` 用于后续 worker 从同一项目/研究的 `ResultStore` artifact 读取输入，不把大 payload 塞进 job JSON；`ArtifactKind.JOB_INPUT` 用于保存 worker 请求 payload。该骨架暂未接入正式数据库、真正任务队列或完整后台管理页；下一步应基于它实现 worker wrapper、SQLite/Postgres 存储和正式历史结果管理。
- 2026-06-15 已新增本地文件版 `LocalResultStore`：`src/green_direct/services/result_store.py` 可按项目/研究保存 `JobArtifact` payload、`StudyResultRecord` 和项目/全局 `AuditLog`，写入产物时自动记录 `storage_uri`、`sha256`、`size_bytes`，并校验路径片段防止路径穿越。该 store 暂未接管现有 Streamlit 工作流，后续应先让技术汇总、经济汇总、推荐组合和导出文件逐步写入 store。
- 2026-06-15 已新增本地账户与项目注册表：`src/green_direct/services/pilot_registry.py` 提供 `LocalPilotRegistry`，支持本地 JSON 用户/项目保存、停用、项目归档、项目成员角色授予和停用；`src/green_direct/services/local_store_utils.py` 抽出本地存储路径校验和 JSON 序列化。该 registry 不存密码、不处理登录会话，后续管理员页和 SQLite/Postgres 存储应基于它继续推进。
- 2026-06-15 已新增本地密码与会话认证服务：`src/green_direct/services/pilot_auth.py` 提供 `LocalPilotAuth`，支持为活跃用户写入 PBKDF2-SHA256 密码哈希、按 `login_name` 登录、创建本地 bearer-token 会话、校验/撤销会话和列出用户会话；会话文件只保存 token 的 SHA256，不保存明文 token；登录成功/失败可写入全局 `AuditLog`。该服务已接入 Streamlit 可选登录门禁，但暂未接入项目权限拦截、企业 IAM、OIDC/LDAP、反向代理认证、CSRF 防护或正式数据库会话表。
- 2026-06-15 已新增平台账号管理服务，并于 2026-06-16 补“恢复账号”和“撤销指定会话”闭环：`src/green_direct/services/pilot_admin.py` 提供 `LocalPilotAdminService`，`User.is_platform_admin` 区分平台管理员和项目 `admin`。该服务支持首个管理员 bootstrap、平台管理员创建用户/设置初始密码/重置密码并撤销目标用户有效会话/授予或撤销平台管理员/停用用户/恢复用户/列出用户、查看和撤销用户会话，以及创建/归档项目、维护项目成员和只读查看审计事件；停用用户会撤销有效本地会话，并阻止停用或降级最后一个活跃平台管理员；恢复用户会重新设为 active 并写 `UPDATE_USER` 审计，密码重置和单会话撤销都会写 `UPDATE_USER` 审计 metadata。该服务已接入 Streamlit 最小平台管理页，后续项目/成员/审计管理 UI 不应直接调用底层 registry/auth/result_store 绕过它。
- 2026-06-15 已新增 `pilot-admin` 命令行运维入口，并于 2026-06-16/17 补项目生命周期/成员、任务运维、worker 认领/heartbeat/终态、failed/canceled 任务手动重试、one-shot/loop worker 执行、审计查看、store doctor、`enable-user` 和 `revoke-session` 命令：源码树运行前需设置 `PYTHONPATH=src`（PowerShell：`$env:PYTHONPATH = "src"`），然后使用 `python -m green_direct.cli pilot-admin ...`；安装为包后也可使用 `green-direct pilot-admin ...`。支持 `doctor`、`bootstrap`、`create-user`、`reset-password`、`disable-user`、`enable-user`、`grant-platform-admin`、`revoke-platform-admin`、`list-users`、`list-sessions`、`revoke-session`、`list-audit-events`、`list-projects`、`create-project`、`archive-project`、`list-project-members`、`grant-project-role`、`disable-project-member`、`list-jobs`、`claim-next-job`、`heartbeat-job`、`complete-worker-job`、`fail-worker-job`、`retry-job`、`run-worker-once`、`run-worker-loop`、`purge-expired-artifacts` 和 `fail-stale-jobs`；密码优先用 `--password-env` 从环境变量读取。默认 store 为 `.runtime/pilot_store`，内部试用部署时应显式传 `--store-dir` 到受控目录。
- 2026-06-15 已把本地认证服务接入 Streamlit 可选登录门禁：设置 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1` 后，主 UI 会先显示登录表单，未登录用户不能进入六步工作流；`GREEN_DIRECT_PILOT_STORE_DIR` 应指向 `pilot-admin --store-dir` 使用的账号目录，默认 `.runtime/pilot_store`。登录态使用 `LocalPilotAuth.require_session()` 校验；会话失效或退出登录会清理当前浏览器会话内的测算结果、下载缓存、价格曲线和图表导出缓存。该门禁仍不是项目级权限、管理员页面、数据库会话或企业 IAM。
- 2026-06-15 已新增 Streamlit 最小“平台管理”页，并于 2026-06-16 补项目生命周期、任务运维、审计日志、恢复停用账号和撤销用户会话入口：仅在 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1` 且当前用户 `is_platform_admin=True` 时显示；平台管理员可创建账号、重置密码并撤销有效会话、停用/恢复账号、授予/撤销平台管理员、查看/撤销会话、创建/归档项目、维护项目成员和导出权限，手动处理一个受支持 queued job / 恢复超时 running 任务元数据，并只读查看全局或项目级审计事件。普通用户看不到入口。该页复用 `LocalPilotAdminService` / `PilotAccessService`，仍不是数据库会话、企业 IAM、审批流、正式审计后台或完整后台管理系统。
- 2026-06-15 已新增上线前质量审查记录：`notes/PRELAUNCH_QUALITY_REVIEW_20260615.md`。当前判断是可进入受控内部 10-20 人 pilot，但不建议公网生产发布；下一轮优先做项目隔离、后台任务 worker、结果存储接入和部署 runbook。
- 2026-06-15 已新增本地任务状态存储，并于 2026-06-16 补 worker/heartbeat、任务列表、卡死任务恢复、queued job 认领原语、failed/canceled 任务手动克隆重试、输入 artifact 引用和协作文件锁：`src/green_direct/services/job_store.py` 提供 `LocalJobStore`，按 `project_id` / `study_id` / `job_id` 保存任务 JSON，支持提交、读取、全局/项目/研究列表、状态筛选、`claim_next_queued_job()` 认领、进度更新、成功/失败/取消状态持久化，并持久化 `Job.input_artifact_ids`；`Job` 模型已增加 `progress_current`、`progress_total`、`progress_message`、`worker_id` 和 `last_heartbeat_at`；`pilot-admin list-jobs` 可由平台管理员查看任务、按状态筛选、显示输入 artifact 数量并标记 stale，`pilot-admin fail-stale-jobs` 可把超时 running 任务标记为 failed 并写 `COMPLETE_JOB` 审计，`pilot-admin retry-job` 可把 failed/canceled 终态任务克隆为新的 queued job 并写 `SUBMIT_JOB` 审计。该 store 只保存任务元数据和本地认领原语，关键状态转换已有协作文件锁但不包含自动重试策略、worker 级资源中断、正式队列或数据库事务；后续后台任务接入应沿用此状态契约。
- 2026-06-16 已新增后台任务 payload artifact 入队 helper：`src/green_direct/services/pilot_study_persistence.py` 提供 `queue_job_with_input_artifact()`，会在提交 queued `Job` 前把非空 JSON 请求 payload 保存为 `ArtifactKind.JOB_INPUT` / `job_input_<job_id>.json`，写 `STORE_ARTIFACT` 审计，并把 `job_payload` 与调用方传入的 `technical_summary`、`config_snapshot`、`input_curve_*` 等外部 artifact 合并到 `Job.input_artifact_ids`。该 helper 只负责持久化输入并入队，不执行计算；下一步按需 hourly detail、经济性补算、图表包和报告导出后台化应优先复用它。
- 2026-06-16 已新增最小 worker 执行路径：`src/green_direct/services/pilot_worker.py` 提供 `execute_next_worker_job()` / `execute_claimed_worker_job()` / `execute_worker_loop()`，当前支持两类任务：`technical_study` + `job_payload.task="hourly_detail"` 会读取 `job_payload`、`technical_summary`、`config_snapshot` 和三条 `input_curve_*` artifact，重建 `TechnicalStudyInput`，复用 `run_hourly_detail_for_scenario()` 补算单方案逐小时明细，写回 `ArtifactKind.HOURLY_DETAIL`；`economic_study` + `job_payload.task="annual_cashflow"` 会读取 `technical_summary`、`recommendation_inputs` 和可选 `power_economy_summary`，为所选固定价/网页组价方案写回 `ArtifactKind.ANNUAL_CASHFLOW`，并拒绝逐时价格曲线结果。两类任务都会写 heartbeat/成功或失败终态审计；`pilot-admin run-worker-once` 可演练一次，`pilot-admin run-worker-loop` 可持续轮询并用 `--max-jobs` / `--idle-exit-after` 做有限运行。任务元数据关键状态转换已有协作文件锁，但该能力仍不是正式队列、重试系统、资源隔离或 worker 级取消。
- 2026-06-16 已在 Streamlit 平台管理页新增“任务运维”tab：平台管理员可查看当前范围内 queued/running job，并手动“处理一个排队任务”。该按钮调用与 `pilot-admin run-worker-once` 相同的 `execute_next_worker_job()` 链路，默认只处理 `technical_study/hourly_detail` 和 `economic_study/annual_cashflow`，用于 Render 单 Web Service 首次内测排障；它不是自动后台守护、正式队列、重试、限流或 worker 级取消。
- 2026-06-16 已把 stale running 任务恢复也接到平台管理页“任务运维”：平台管理员可把超过 `PILOT_JOB_STALE_AFTER_SECONDS` 未 heartbeat 的 running 任务元数据标记为 failed；CLI `fail-stale-jobs` 也改为复用 `PilotAccessService.fail_stale_running_jobs_for_platform_admin()`。该能力只修复任务状态和审计，不会终止或回收真实 Python/系统进程。
- 2026-06-16 已新增平台管理员手动重试 failed/canceled 任务：`PilotAccessService.retry_terminal_job_for_platform_admin()` 和 `pilot-admin retry-job` 会在原始请求人仍有提交权限、原始 input artifact 仍存在时，把终态任务克隆为新的 queued job，保留原请求人、任务类型、输入 fingerprint 和 artifact 引用，并写入 `SUBMIT_JOB` 审计 metadata。它不会修改原任务，不会重试 queued/running/succeeded 任务，也不是自动重试策略。
- 2026-06-16 已把按需逐小时明细后台化入口接到 Streamlit，并补第一版前台轮询/自动加载：`_render_on_demand_hourly_detail_action()` 在所选方案缺少 hourly detail 且项目结果已保存 `technical_summary`、`config_snapshot` 和三条 `input_curve_*` artifact 时，会显示“提交后台补算”，调用 `queue_job_with_input_artifact()` 提交 `technical_study/hourly_detail` queued job；若任务处于 queued/running，当前区域用 `st.fragment(run_every="5s")` 轮询任务状态；若任务 succeeded，UI 会刷新当前 `StudyResultRecord.hourly_detail_artifact_ids`，把 `hourly_detail_<scenario_id>` 挂回 `StudyResult.result_store_refs`，并加载 artifact 到当前 `batch_result.hourly_details`。若当前会话仍有 `TechnicalStudyInput`，同步补算按钮继续保留。该能力只覆盖当前按需明细区域，还不是全局任务通知、worker 级取消/重试或全量技术/经济任务后台化。
- 2026-06-15 已新增本地权限与审计服务门面，并于 2026-06-16 补平台管理员保护的 worker 认领、heartbeat、成功/失败终态入口、failed/canceled 任务手动重试、CLI 演练入口和任务输入 artifact 校验：`src/green_direct/services/pilot_access.py` 提供 `PilotAccessService`，组合 `LocalPilotRegistry`、`LocalJobStore` 和 `LocalResultStore`，集中校验 `admin` / `analyst` / `viewer` 项目权限，支持项目创建/归档、成员授权/停用、任务提交/查看/取消、worker 认领、worker heartbeat/进度、worker 终态、终态任务克隆重试、产物读取，并对关键动作写入 `AuditLog`。`submit_job()` 会校验 `Job.input_artifact_ids` 指向同一 `project_id` / `study_id` 下已存在 artifact，并把引用写入 `SUBMIT_JOB` 审计 metadata；`claim_next_job_for_worker()` 可全局或按项目认领 queued job，服务层会跳过归档项目；`update_worker_job_progress()`、`succeed_worker_job()`、`fail_worker_job()` 要求平台管理员和匹配的 `worker_id`，只更新 running job；`retry_terminal_job_for_platform_admin()` 只接受 failed/canceled 原任务并生成新的 queued job；`pilot-admin claim-next-job` / `heartbeat-job` / `complete-worker-job` / `fail-worker-job` / `retry-job` 可演练 worker 元数据流程，`run-worker-once` 和 `run-worker-loop` 已可执行按需 hourly detail 与固定价/网页组价 annual cashflow worker 链路。该服务仍不包含密码登录、会话认证、管理员 UI、正式队列、自动重试策略或数据库事务；后续 Streamlit 管理页、后台任务入口和 SQLite/Postgres 适配器应优先调用它，不要直接绕过权限门面。
- 2026-06-15 已新增技术仿真结果持久化第一阶段：`src/green_direct/services/pilot_study_persistence.py` 提供 `persist_technical_study_result()`，在启用 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1` 且用户已选择项目时，Streamlit Demo 和正式技术仿真完成后会登记项目级同步 `technical_study` Job，写入 `technical_summary.csv`、`config_snapshot.json` 和 `StudyResultRecord(result_id="technical_result")`，并把 `project_id`、`technical_job_id`、`technical_result_id`、`technical_summary_artifact_id`、`config_snapshot_artifact_id` 挂到 `StudyResult.result_store_refs`。随后已补 `persist_hourly_detail_artifact()`，当前会话按需补算的单方案逐小时明细可写成 `ArtifactKind.HOURLY_DETAIL` CSV 并挂回 `hourly_detail_artifact_ids`。这仍不是后台 worker；图表包和报告仍待迁移到 `ResultStore`。
- 2026-06-15 已新增项目任务与结果索引面板：`LocalResultStore` 和 `PilotAccessService` 可按项目/研究列出 `StudyResultRecord`，Streamlit 欢迎页在启用内部试用登录且选中项目后显示“项目任务与结果”，列出当前项目任务数、已保存结果数、最近任务和最近结果索引。随后已补“历史结果产物”区，可加载并下载已落盘的技术 summary、经济 summary、已保留年度现金流、推荐席位输入、推荐 portfolio/detail 等 artifact；技术 summary 可 summary-only 恢复到当前会话，写回 `batch_result.summary` / `study_result` / `config_snapshot`，并保留已有 hourly artifact 索引用于后续图表/报告入口加载；同一 `study_id` 的技术 summary 已恢复后，经济结果可恢复 summary、已保留年度现金流和推荐席位输入，推荐 portfolio 可 portfolio-only 恢复到当前会话。网页内恢复/查看 payload 走 `PilotAccessService.read_artifact_payload_for_view()` 并写 `VIEW_ARTIFACT` 审计；文件下载 payload 仍走 `read_artifact_payload()` 并要求导出权限。该面板仍不支持完整历史 `StudyResult`、推荐视角选择/重新排序工作台状态恢复，也不支持删除、标记、完整历史页或跨项目搜索。
- 2026-06-15 已新增经济性与推荐结果持久化第一阶段，并于 2026-06-16 补推荐席位输入、年度现金流和第一片导出产物 artifact：`persist_economic_study_result()` 会登记项目级同步 `economic_study` Job，写入 `power_economy_summary.csv`、`single_entity_summary.csv`、`recommendation_inputs.json`、当前运行实际保留的 `power_annual_cashflows.zip` / `single_entity_annual_cashflows.zip` 和 `StudyResultRecord(result_id="economy_result_<job_id>")`；`persist_annual_cashflow_artifact()` 可把按需补算的单方案年度现金流以 `power:<scenario_id>` / `single_entity:<scenario_id>` 挂回既有经济结果；`persist_recommendation_study_result()` 会登记 `recommendation` Job，写入 `recommendation_portfolio.csv`、`recommendation_load_side_detail.csv` 和 `StudyResultRecord(result_id="recommendation_result_<job_id>")`；`persist_export_artifact()` 会登记 `chart_export` / `report_export` Job，06 导出页可把所选方案 HTML 图表包和简版 Markdown 报告显式保存为默认 7 天过期的 `chart_package` / `report` artifact。Streamlit 03 页经济性测算成功后会写经济 summary、已保留年度现金流和推荐席位输入，推荐页会按 fingerprint 去重写推荐组合。推荐视角选择/重排状态、PNG/Excel/批量导出包、完整报告、全量经济性后台化和价格曲线年度现金流补算仍待迁移。
- 2026-06-15 已把大批量“汇总优先”接入 02 页：`simulation_large_run_hourly_detail_limit` 默认 20；当候选方案数超过 `simulation_warn_threshold` 时，`TechnicalStudyInput` 会传 `retain_hourly_details=False` 和前 N 个 `S0001...` 方案 ID，只常驻保存方案汇总和少量逐小时明细。该策略不改变调度口径；若当前有项目级下网电价曲线，会清除并切回固定价/网页组价，避免价格曲线经济性缺少全量逐小时明细。后续仍需做后台 worker 进度和取消闭环。
- 2026-06-16 已把技术仿真汇总优先从“只少存明细”推进为真正 summary-only 执行路径：`run_single_scenario(..., retain_hourly_detail=False)` 仍逐小时执行同一 dispatch/SOC 逻辑并累计 summary，但不构造完整 `hourly_detail` DataFrame；`run_batch()` 只为全量保留或指定保留的方案生成 ledger，其余方案只返回 summary。小基准：120 个 8760 小时方案完整保留明细约 7.822s，summary-only 约 4.941s，约 1.58x。该优化不改变 V0.1 调度口径；价格曲线、图表、报告仍需要被保留或后续按需补算的逐小时明细。
- 2026-06-16 已把技术仿真并行路径从“每个方案一个进程池 task”改为自动按方案块提交给 `ProcessPoolExecutor`：块内仍逐方案调用同一 `run_single_scenario()`，但大方案池下的 task 提交数量显著减少；`executor.map` 仍按输入块顺序返回，`scenario_id`、warning、error 和 progress callback 顺序保持稳定。小样本验证：57 个方案、168 小时、2 worker、summary-first 路径约 1.2143s。
- 2026-06-16 已继续减少技术仿真逐小时热路径固定开销：`dispatch_hour()` 保留公开接口，`dispatch_hour_with_limits()` 保留 dataclass 兼容接口，`dispatch_hour_values_with_limits()` 返回轻量 values 供 `run_single_scenario()` 热路径直接消费；`run_single_scenario()` 在循环外缓存 scenario/Policy/BESS 常量、`dt_hours` 倒数和曲线 numpy 数组，循环内避免为每小时创建 `DispatchStep` dataclass。189 个方案、168 小时 benchmark 中 technical summary-first 曾从 3.9668s 降到 3.8365s，本轮重复样本约 3.36-3.64s；572 个方案、168 小时样本约 10.3127s。该优化不改变 V0.1 调度口径。
- 2026-06-16 已新增单次方案数硬上限：`PerformanceParams.max_scenarios_per_run` 会让 `run_batch()` 在正式调度前拒绝超限方案池；Streamlit 02 页读取 `GREEN_DIRECT_MAX_SCENARIOS_PER_RUN`，默认 20,000，超限时显示错误并禁用“开始测算”。Dockerfile、docker-compose、`.env.example`、部署 README、安全说明、性能路线和审计矩阵已同步。该能力只是同步计算阶段的 guardrail，不是后台 Job、取消、排队或资源隔离。
- 2026-06-17 已把方案数预估和硬上限拒绝改为轴计数路径：`estimate_scenario_count()` 不再构造完整 `Scenario` 列表，也不展开光伏容量轴 × 风电容量轴；`run_batch()` 会先拒绝超限方案池再物化可执行方案；`generate_scenarios()` 也预计算容量轴和储能功率/时长组合，减少大方案池启动前固定开销。25,596 个候选方案样本中，方案数预估约从 0.0407s 降到 0.000052s，方案对象生成约从 0.0410s 降到 0.0296s；理论 1,999,999,999,998 个候选组合的巨大样本只做预估约 0.000067s。该优化不改变 scenario_id 顺序、过滤规则或调度口径。
- 2026-06-17 已新增无储能 summary-only 技术仿真快路径：`run_single_scenario(..., retain_hourly_detail=False)` 在无储能方案下用 NumPy 数组直接汇总直供、下网、上网、弃电、年上网比例 cap、站用电和电网交换限额，再复用 `calculate_summary_from_values()`；完整逐小时明细和有储能 SOC 滚动仍走原逐小时 dispatch 路径。混合 105 方案、168 小时样本技术 summary-first 约从 1.7635s 到 1.6219s；无储能且不保留明细 35 方案、168 小时样本约 0.0586s。该优化不改变 V0.1 调度口径。
- 2026-06-17 已继续把无储能 retained hourly detail 也改为 NumPy 快路径：无储能方案保留逐小时明细时不再逐小时调用 dispatch helper，而是用同一组数组构造 `HOURLY_LEDGER_COLUMNS` 后复用 `calculate_summary()`；新增测试用原始 dispatch helper 生成参考结果并 monkeypatch 热路径，证明 full-detail 快路径不调用逐小时 dispatch 且关键 ledger 字段一致。无储能、保留 20 个明细的 35 方案/168 小时样本约从 0.3967s 到 0.1809s；有储能 SOC 路径未变，仍是后续性能重点。
- 2026-06-17 已继续优化有储能热路径：`run_single_scenario()` 在进入有储能逐小时循环前，预计算光伏/风电出力、正负出力拆分、站用电、净可用绿电、调度负荷和逐小时电量数组；循环内仍调用同一 `dispatch_hour_values_with_limits()` 并滚动 SOC。189 个方案、168 小时、summary-first 且不保留明细样本约从 2.3252s 到 1.2666s；30 个方案、168 小时、完整明细保留样本约 0.3194s。该优化不改变 V0.1 dispatch、hourly ledger 字段或 summary 口径。
- 2026-06-17 已让批量技术仿真复用同一份曲线数组：`prepare_curve_data()` 把 timestamp、负荷、光伏、风电列提取为 `PreparedCurveData`，`run_batch()` 在串行和并行 worker 初始化时只准备一次，然后传给每个 `run_single_scenario()`。189 个方案、168 小时、summary-first 且不保留明细样本约从 1.2250s 到 1.1194s；cProfile 函数调用数约从 514,076 降到 400,521，DataFrame 取列和 `to_numpy()` 不再是每方案热点。公开单方案仍可直接传 `DataFrame`。
- 2026-06-17 已继续瘦身有储能 dispatch 热路径：新增 `dispatch_bess_hour_values_with_limits()`，`run_single_scenario()` 有储能路径直接调用该 helper，保留原 public `dispatch_hour*` 兼容接口；未配置 `grid_exchange_power_limit` 时跳过每小时 `min(..., inf)` 和交换限额短缺/弃电原因计算。189 个方案、168 小时、summary-first 且不保留明细样本约从本轮基线 1.0011s 到 0.9364s；cProfile 函数调用数约从 400,521 降到 379,353，`min()` 调用约从 63,567 降到 42,399。该优化不改变 V0.1 BESS SOC 滚动、上网比例 cap、并网交换限制、summary 字段、经济性 V1 或推荐排序；下一步仍应推进后台 Job/worker 和更大的计算内核优化。
- 2026-06-16 已新增计算前粗略耗时提示与大批量确认：02 页会按方案数、输入小时数、明细保留策略和并行进程数显示粗略预计耗时；超过方案数提醒阈值时，必须勾选“大批量同步测算确认”后才允许开始。确认状态绑定工作量签名，方案数、小时数、并行进程、明细保留数或明细模式变化会自动重置。该估算只是一版前台 guardrail，不是精确 SLA，也不替代后台 worker。
- 2026-06-16 已新增单方案逐小时明细按需补算：服务层 `run_hourly_detail_for_scenario()` 从 `summary` 行重建 `Scenario`，复用 `TechnicalStudyInput` 中的原始曲线、BESS、Policy 和 `dt_hours`，只跑选中方案并返回完整 `ScenarioResult.hourly_detail`。Streamlit 推荐页、图表概览页和导出/报告页在所选方案缺明细时会先尝试加载已有项目级 `hourly_detail_<scenario_id>` artifact；没有可用 artifact 时，若项目结果已有 summary/config/input curve artifacts，可提交后台 `technical_study/hourly_detail` job，当前按需明细区域会轮询任务状态并在任务成功后加载 artifact；若当前 session 有 `_technical_study_input`，仍可同步补算。同步补算成功后会写回当前 `batch_result.hourly_details` 与 `study_result.technical_result.batch_result`，清空旧下载和图表缓存，并把补算明细写成默认 30 天过期的项目级 `ArtifactKind.HOURLY_DETAIL`，写 `STORE_ARTIFACT` 审计。
- 2026-06-16 已新增项目活动任务查看、任务状态明细与取消入口第一版：Streamlit 欢迎页“项目任务与结果”面板会筛出当前项目 `queued` / `running` 活动任务，并展示完整任务状态、进度、worker、最后 heartbeat、stale 标记和错误说明；`analyst` 只能取消自己发起的活动任务，项目 `admin` 可取消项目内活动任务，`viewer` 和终态任务不可取消。取消动作调用 `PilotAccessService.cancel_job()`，继续做后端权限校验和 `CANCEL_JOB` 审计。该能力只是任务元数据控制入口，不会中断正在运行的 Python 计算进程；真正 worker 轮询、worker 级取消、排队和重试仍待实现。
- 2026-06-15 已吸收受控公网内测 Route A 讨论稿方向：近期上线仍优先是内部 10-20 人 pilot；若开放公网访问，必须保持邀请制账号、不接真实电力控制系统、补独立可导出/不可导出权限、上传文件安全、仓库外产物存储、审计日志、留存清理、HTTPS/反向代理、备份恢复和回滚说明。当前 `viewer` / `analyst` / `admin` 项目角色不能直接等同于公网内测的导出授权角色。
- 2026-06-15 已落地导出授权第一版，并于 2026-06-16 补当前导出页临时下载审计：`ProjectMembership.can_export_artifacts` 独立于 `admin` / `analyst` / `viewer` 控制下载/导出；`LocalPilotRegistry`、`LocalPilotAdminService` 和 `PilotAccessService` 均已透传该字段；`PilotAccessService.read_artifact_payload()` 要求导出权限，成功和拒绝都会写入 `DOWNLOAD_ARTIFACT` 审计；`read_artifact_payload_for_view()` 只用于网页内恢复/图表查看，要求项目查看权限并写 `VIEW_ARTIFACT` 审计，不应被未来下载 API 复用；`record_transient_export_download()` 用于当前 06 页尚未落盘为 artifact 的 CSV/Excel/ZIP/Markdown 下载按钮，复用导出权限并写同类审计；Streamlit 平台管理页可维护“允许下载/导出项目结果”，欢迎页历史 artifact 下载和 06 导出页会按当前项目成员权限拦截，HTML 图表包和 Markdown 报告保存还要求项目 Job 提交权限。后续未来 API、反向代理下载路径、对象存储签名 URL 和数据库适配仍必须复用这层语义。
- 2026-06-15 已落地上传文件安全第一版：新增 `src/green_direct/services/upload_policy.py`，默认单文件上限 20MB，可用 `GREEN_DIRECT_MAX_UPLOAD_MB` 调整；Streamlit 02 页批量上传和单独上传会先校验后缀/大小，技术曲线只允许 CSV，下网电价曲线允许 CSV/XLSX/XLSM；合法上传文件的文件名、后缀、大小和 SHA256 写入 `config_snapshot["upload_file_metadata"]`。这不是完整原始文件留存和清理机制，后续仍需仓库外隔离存储、过期清理和关键 Run 保留。
- 2026-06-17 移动宽度 UI 冒烟发现上传控件提示与应用策略不一致：Streamlit 默认显示 `200MB per file`，但应用和部署默认 `GREEN_DIRECT_MAX_UPLOAD_MB=20`。已让 Docker CMD、smoke 脚本、本地启动器和部署 runbook 显式传入 `--server.maxUploadSize`，默认与 `GREEN_DIRECT_MAX_UPLOAD_MB` 对齐；Docker 仍允许用 `STREAMLIT_SERVER_MAX_UPLOAD_SIZE` 覆盖。后续手写 `streamlit run` 时也应带该参数，避免公网试用用户看到错误上传上限。
- 2026-06-16 已新增技术三曲线 input artifact 留存与跨会话输入恢复第一版：`persist_technical_study_result()` 可接收 `TechnicalStudyInput`，并在技术结果写入项目 `ResultStore` 时，把负荷、光伏、风电三条输入曲线分别保存为 `ArtifactKind.INPUT_CURVE`：`input_curve_load`、`input_curve_pv`、`input_curve_wind`；默认 30 天过期，写 `STORE_ARTIFACT` 审计，`config_snapshot.json` 会写入 `input_artifact_ids`、`curve_columns` 和 `cleaning`。Streamlit Demo 和正式技术仿真路径已传入当前 `TechnicalStudyInput`；历史 summary-only 恢复时会带回 input artifact 索引，图表/报告入口可通过 `read_artifact_payload_for_view()` 读取 input artifact、重建 `TechnicalStudyInput`，再按需补算缺失 hourly detail。不可导出用户仍只能网页查看/补算，不能下载 artifact payload。
- 2026-06-15 已落地 artifact 留存清理第一版：`JobArtifact` 新增 `retention_policy`、`expires_at` 和 `purged_at`；`LocalResultStore.purge_expired_artifacts(now=...)` 会删除到期 payload、保留 `artifact.json` 元数据和历史索引；`pilot-admin purge-expired-artifacts --actor-user-id <admin>` 要求平台管理员执行，并为每个清理的 artifact payload 写入项目级 `DELETE_ARTIFACT` 审计。该能力仍不是定时任务、对象存储生命周期策略或原始上传文件清理；后续应补后台调度、仓库外数据卷、关键 Run 保留和恢复说明。
- 2026-06-16 已新增内部试用部署材料第一版：`.env.example` 记录多人 pilot 环境变量口径；`docs/INTERNAL_PILOT_DEPLOYMENT_RUNBOOK.md` 记录部署边界、目录规划、首个管理员 bootstrap、服务器启动命令、备份、恢复、过期清理、冒烟检查和回滚；`scripts/backup_pilot_store.ps1` / `scripts/restore_pilot_store.ps1` 可对 pilot store 做 ZIP 备份和恢复到空目录。脚本已通过 PowerShell 语法解析，并用 `.runtime` 临时 store 跑通过备份/恢复内容校验。该材料仍不是 HTTPS/反向代理、系统服务、日志轮转、监控和 CI/CD 的完整生产部署包。
- 2026-06-10 02 页“指定单方案”输入已做去冗和排版修正：模式入口保留“指定单方案”，但字段标签只写“光伏容量、风电容量、储能功率、储能容量”；四个输入采用两行两列，不再一行四列挤压中文标签。03 页经济性参数工作台也继续压紧：基本参数行改为四列节奏，Year 0 建设投资六个输入放到同一行，减少大块空白。后续新增参数控件时，优先让入口表达模式、字段表达名词，避免每个控件重复解释当前模式，也不要让少量字段横向撑满全屏。
- 2026-06-10 已进一步确认 UI 改造不能过度守旧：保留计算口径不等于保留旧页面结构。03 页经济参数已从单一“经济性参数工作台”大框拆为运行口径、建设投资、运维成本、收入和税金、到户电价展示、高级参数六个小工作卡；参数被放入 `st.form("economy_v1_params_form")`，顶部和底部都有“计算经济性 V1”提交按钮。表单内编辑常调参数时不再触发整页 rerun，浏览器测得风电单位造价输入改动前端响应约 82ms。后续 UI 工作应围绕“快速完成方案策划、经济测算、推荐和交付”主目标，不要为了沿用旧大表单而牺牲交互流畅性。
- 2026-05-25 已新增独立方案遍历试用程序入口：`src/green_direct/services/batch_trial_runner.py`、`src/green_direct/ui/batch_trial_gui.py`、`packaging/pyinstaller/run_batch_trial_tool.py`、`GreenDirectBatchTrial.spec` 和 `scripts/build_batch_trial_exe.ps1`。该入口只包装三条 CSV 读取、风光储容量枚举、逐小时技术仿真、方案概览 Excel 和全部方案逐小时详表 ZIP，不代表长期主产品要回到全量枚举表优先；配套说明见 `docs/BATCH_TRIAL_TOOL_USER_GUIDE.md` 和 `docs/BATCH_TRIAL_DISPATCH_AND_CALCULATION.md`；
- 下一步建议继续把当前项目任务状态明细升级为真正 worker 重试/取消页面，在已有 queued job 认领原语、任务 payload、one-shot/loop worker、手动克隆重试、协作文件锁、UI 后台补算入口和按需明细轮询加载基础上补正式队列、worker 级取消、自动失败重试策略、数据库级并发控制和全局任务通知；继续补完整历史结果恢复/下载/删除、summary-only 经济运行的按需年度现金流 Job、推荐视角选择与重新排序工作台状态、剩余导出页和图表模块从兼容层 `batch_result` / session_state 逐步迁移到 `StudyResult` + `ResultStore` 读取；完善 `recommendation/` 模块的数据模型和导出契约，并为典型日选择、PNG/Excel/批量包、完整报告输出补充更细的审计数据。
