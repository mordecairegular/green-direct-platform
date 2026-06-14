# Claude Code 内部试用上线提示词

本文用于把当前项目交给 Claude Code 做两类工作：

1. 内部 10-20 人试用上线前 review/debug；
2. 在不改变计算口径的前提下提升 Streamlit UI。

## 1. 对现有 GPT 提示词的判断

现有提示词方向是对的：应该把 Claude Code 分成“上线审查”和“UI 提升”两轮，而不是让它一次性同时做安全、性能、架构和视觉改造。

但原提示词还需要补强四点：

- 明确审查范围：要求 Claude Code 先确认当前分支、最近提交和工作区状态；
- 明确修复权限：P0/P1 可直接修，但任何计算口径变化必须先说明原因，并同步测试和文档；
- 明确 UI 边界：只优化当前 Streamlit 工程工作台，不重写为新前端，不把全量枚举表变成主入口；
- 明确交付证据：每轮都要给文件、行号、复现路径、验证命令和浏览器检查结果。

## 2. 使用顺序

建议按下面顺序给 Claude Code：

1. 先发送“上下文读取提示词”；
2. 再发送“上线前 review/debug 提示词”；
3. 如果 P0/P1 清零，再发送“UI 提升提示词”；
4. 如果要继续推进多人后台，再发送“后台账户、Job 和 ResultStore 架构提示词”。

不要把第 2 步和第 3 步合并。审查阶段要保守，UI 阶段要有设计判断，两者混在一起容易漏掉真正的上线风险。

## 3. 上下文读取提示词

```text
请先不要改代码。请阅读 AGENTS.md、CLAUDE.md、notes/HANDOFF_FOR_NEW_MACHINE.md、notes/PRODUCT_POLISH_LOG.md、docs/INTERNAL_PILOT_ARCHITECTURE_PLAN.md、docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md、docs/ECONOMY_RECOMMENDATION_V1_MAP.md、docs/CHART_MODULE_CURRENT_LOGIC.md、docs/WEB_APP_WORKFLOW_AND_UI_RESTRUCTURE.md，以及 notes/architecture_reframe_20260519/ 下的文档。

读完后请用中文简要说明：
1. 当前项目定位；
2. V0.1 风光储技术仿真基线；
3. 内部 10-20 人试用上线边界；
4. 当前已做的多用户隔离和性能优化；
5. 后续开发时你会如何避免破坏计算口径。

然后执行：
git status --short --branch
git log --oneline -8
python -m pytest -q

请把当前分支和工作区视为既有工作，不要回滚用户或其他 agent 已经做出的改动。
```

## 4. 上线前 review/debug 提示词

```text
请按“内部 10-20 人试用上线前审查”全面 review/debug 当前项目。

审查范围：
1. 当前工作区；
2. 当前分支相对远端的新增提交，优先查看：
   git log --oneline origin/codex/UI..HEAD
   git diff --stat origin/codex/UI...HEAD
   如果没有 origin/codex/UI，请改用最近 5 个提交作为审查范围；
3. Streamlit 前台、服务层、批量技术仿真、经济性测算、推荐、图表/导出、启动器和测试。

重点审查：
1. 多人部署风险：
   - 是否存在跨用户 session_state 串数据；
   - 是否存在进程级全局缓存复用用户结果；
   - `.runtime/latest_session_snapshot.pkl` 是否会在多人环境默认恢复旧结果；
   - PNG/HTML/Excel/CSV/Markdown 下载是否可能拿到旧项目或其他用户的数据；
   - 下网电价曲线是否只来自当前会话明确上传的数据。
2. 后台任务风险：
   - PNG ZIP 后台任务 key 是否按会话隔离；
   - 新技术仿真后旧导出缓存是否失效；
   - 长任务失败、取消、重复点击、页面切换后的状态是否可恢复或可解释。
3. 计算口径风险：
   - V0.1 储能只能由富余新能源充电；
   - 储能不得从电网充电；
   - 储能不得放电上网；
   - 同小时不得同时充放电；
   - SOC 滚动、上下限、功率和容量约束不被破坏；
   - 支持 8760 和 8784 行；
   - 经济性、推荐、图表和报告只读取技术仿真结果，不反向改变调度。
4. 性能风险：
   - 成千上万方案时是否仍强制保留所有逐小时明细；
   - `retain_hourly_details`、`hourly_detail_scenario_ids`、`retain_annual_cashflows`、`parallel_workers` 的默认行为和 UI 接入是否一致；
   - 并行技术仿真是否保持 scenario_id、warning、error、进度和结果顺序稳定；
   - 经济性测算是否有继续批量化的明确下一步。
5. UI 和交付风险：
   - 六步工作流是否能从 Demo 跑通到推荐、图表和导出；
   - 错误提示是否能让内部试用用户知道下一步；
   - raw scenario enumeration 是否被放回主入口；
   - 图表模块是否被过度当成稳定架构锚点。

输出要求：
1. 先列 Findings，按 P0/P1/P2 排序；
2. 每个 finding 必须包含文件路径、行号、复现方式、风险说明和建议修复；
3. P0/P1 如果不改变计算口径，可以直接修复；
4. 任何可能改变计算口径、经济性口径或推荐口径的修复，必须先说明原因，并同步测试和文档；
5. 最后列出已运行的验证命令、未能验证的风险和下一步建议。

完成后请运行：
python -m pytest -q

如果修改了前端，请用浏览器打开本地 Streamlit，至少检查 01 项目启动、02 方案仿真、03 经济测算、04 方案推荐、05 图表概览、06 下载报告没有明显异常。
```

## 5. UI 提升提示词

```text
请在不改变核心计算口径的前提下提升当前 Streamlit UI。

目标用户：
内部能源项目规划人员、技术经济测算人员和项目负责人。界面应像工程测算和规划辅助决策后台，而不是营销首页或展示型网站。

目标体验：
1. 01 项目启动：让用户快速知道输入是否齐备、结果是否可用、下一步该做什么；
2. 02 方案仿真：让曲线上传、方案池、政策约束、性能设置更清晰，避免把全量枚举表作为主入口；
3. 03 经济测算：提高参数分组和输入密度，减少大面积空白和反复 rerun；
4. 04 方案推荐：强化推荐席位、命中理由、风险提示和关键技术经济指标；
5. 05 图表概览：围绕代表方案和用户加入的对比方案组织图表，而不是围绕全部枚举结果；
6. 06 下载报告：清楚展示哪些文件已准备好、哪些需要先运行计算、导出失败如何处理。

允许做：
1. 调整文案、分组、折叠区、状态提示、按钮位置、信息密度和页面层级；
2. 增加必要的输入校验和用户友好错误提示；
3. 增加轻量 CSS 和 Streamlit 组件布局优化；
4. 为 UI 行为补充测试；
5. 删除明显重复或误导的界面文案，但不要删除功能入口。

不允许做：
1. 不要改 V0.1 技术调度口径；
2. 不要改经济性和推荐算法；
3. 不要把 Streamlit 重写为 React、Vue、FastAPI 或其他新架构；
4. 不要把 raw scenario enumeration 变成主页面核心体验；
5. 不要把图表模块当成不可替换架构锚点；
6. 不要为了视觉效果隐藏关键单位、计算口径和风险提示。

交付要求：
1. 每个 UI 改动都说明对应的用户任务；
2. 给出修改文件清单；
3. 运行 python -m pytest -q；
4. 用浏览器实际打开本地 Streamlit，检查六个页面；
5. 如果发现 UI 问题但本轮不修，请列为 P2/P3 后续项。
```

## 6. 后台账户、Job 和 ResultStore 架构提示词

```text
请先做架构设计，不要一次性实现完整后台。

目标是支持内部 10-20 人试用，不是正式公网 SaaS。请先阅读 `src/green_direct/models/pilot_backend.py`、`src/green_direct/services/result_store.py`、`src/green_direct/services/pilot_registry.py`、`src/green_direct/services/pilot_auth.py`、`src/green_direct/services/pilot_admin.py`、`src/green_direct/services/job_store.py` 和 `src/green_direct/services/pilot_access.py`，把它们视为已经落地的第一步模型、本地文件版 ResultStore、本地账户/项目注册表、本地密码/会话认证服务、本地平台账号管理服务、本地任务状态存储和本地权限/审计服务，再基于当前 Streamlit 前台和 Python 服务层，设计下一阶段最小后台能力：
1. User、Role、Project、ProjectMembership；
2. ProjectStudy、StudyResult、ResultStore；
3. Job、JobStatus、JobArtifact；
4. AuditLog；
5. 技术仿真、经济性测算、推荐组合、PNG/HTML/Excel/Markdown 导出的后台任务化；
6. 输入文件、结果文件和下载文件的隔离策略；
7. 与现有 `run_technical_study()`、`run_economic_study()`、`build_recommendation_study()` 的衔接方式。

请输出：
1. 最小数据模型；
2. 一期实现切片，要求每片都能独立测试和回滚；
3. 哪些部分可以继续留在 Streamlit，哪些必须抽到服务层；
4. 多用户部署时必须禁止或改造的现有机制；
5. 测试计划；
6. 迁移风险。

不要改变当前 V0.1 计算口径。不要为了后台架构一次性重写整个项目。
```
