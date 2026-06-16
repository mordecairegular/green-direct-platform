# 性能优化路线：方案遍历与经济性测算

日期：2026-06-16

本文面向内部 10-20 人试用和后续受控公网内测 Route A。目标是在不改变 V0.1 风光储逐小时调度口径、不改变经济性 V1 现金流口径的前提下，降低大方案池等待时间、内存占用和导出压力。

## 1. 当前结论

当前性能问题不是单点 bug，而是产品形态从“少量方案本地测算”走向“多人、多项目、大方案池”后的系统性压力。

主要瓶颈：

- 技术仿真仍需逐小时滚动 dispatch/SOC，方案数上千后总耗时线性增长；
- 如果每个方案都构造并常驻 8760/8784 行逐小时明细，内存、序列化、快照和 UI 都会变重；
- 经济性 V1 对每个方案生成年度现金流并求 FIRR，方案数大时也会变慢；
- Streamlit 进程内同步计算不适合多人同时运行大任务。

已落地的第一步：

- `run_single_scenario(..., retain_hourly_detail=False)` 已支持 summary-only，不再为未保留方案构造完整 `hourly_detail`；
- `run_batch(..., retain_hourly_details=False, hourly_detail_scenario_ids=...)` 已支持汇总优先和指定方案明细保留；
- `PerformanceParams.parallel_workers` 已支持 `ProcessPoolExecutor` 并行技术仿真；
- 并行技术仿真已改为自动按方案块提交给进程池，减少大方案池下一个方案一个 task 的调度开销，结果聚合仍保持方案顺序；
- 02 页已暴露并行进程数和大批量保留明细数；
- `PerformanceParams.max_scenarios_per_run` 与 `GREEN_DIRECT_MAX_SCENARIOS_PER_RUN` 已提供单次方案数硬上限；02 页会在超限时提示并禁用开始测算，`run_batch()` 后端也会拒绝执行；
- `estimate_scenario_count()` 已改为轴计数路径，不再为方案数预估构造完整 `Scenario` 列表，也不展开光伏容量轴 × 风电容量轴；`run_batch()` 会先用该路径做硬上限判断，再生成可执行方案池；
- `generate_scenarios()` 已把容量轴和储能功率/时长组合移到嵌套循环外预计算，减少大方案池枚举前的固定开销；
- 02 页已新增计算前工作量提示：按方案数、小时数、明细保留策略和并行进程数给出粗略耗时区间；超过方案数提醒阈值时必须勾选大批量同步测算确认，才允许点击“开始测算”；
- 推荐页、图表页和导出页已支持当前会话内对单方案按需补算逐小时明细；
- `run_economic_study(..., retain_annual_cashflows=False, annual_cashflow_scenario_ids=...)` 已支持只常驻经济性 summary 或指定方案年度现金流；未保留年度现金流的方案已不再构造完整年度现金流 `DataFrame`，也不再构造逐年现金流表 row dict，只保留计算 summary 指标所需的现金流数组；
- Streamlit 03 页已接入经济性现金流保留策略：默认 `GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD=1000`，超过阈值时仍计算全量经济性 summary、FIRR/NPV 和推荐排序，但只常驻前 `GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT=20` 个方案年度现金流；06 页会解释未常驻现金流的方案为什么没有年度现金流下载按钮；
- 06 页已接入固定价/网页组价经济性结果的按需年度现金流后台任务：缺少所选方案现金流时可提交 `economic_study/annual_cashflow` queued job，worker 读取 `technical_summary` 和 `recommendation_inputs` 后为所选方案生成电源侧/同一主体年度现金流 artifact，并由导出页轮询加载；
- 经济性批量评价已减少 `iterrows()`、重复校验、未保留年度现金流表构造和部分 IRR 求解开销；
- 经济性批量评价已缓存 `other_operating_revenues` 年度生效表，并把同一方案内每年不变的电源侧收入、VAT 拆分、O&M 和基础折旧移出年度循环，减少大方案池下每方案固定开销；随后又新增电源侧和同一主体批量评价共享上下文，把全方案共用的折现因子、固定资产拆分、其他收入年度表和默认电价口径预处理到批量入口；批量 summary-only 内部复用空年度现金流表哨兵，公开单方案调用仍保持独立空表语义；这些优化不改变 V1 现金流口径。
- FIRR 求解已为常见储能更换临时现金流下凹增加快路径：当现金流是“初始投资为负、运营期主要为正、中间更换年短暂小幅转负、紧接后续现金流可覆盖该下凹、之后恢复为正”时，直接用同一个 bisection 根求解，不再扫描完整候选利率网格；真正末尾转负、下凹后恢复不足或大幅非传统现金流仍回退到原多根扫描并保留多 IRR 拒绝语义。
- FIRR 多根 fallback 的候选利率扫描已改为 NumPy 批量 NPV 和符号穿越区间识别：候选利率列表、唯一根/多根判定和最终 bisection 求根语义不变，但不再为每个方案逐候选点执行 Python NPV 热循环；5,000 行 synthetic economic summary 的 `run_economic_study(..., retain_annual_cashflows=False)` 直接计时约从 18.3s 降到 1.0s。
- 单方案逐小时调度热路径已新增预计算限额和轻量返回入口：`dispatch_hour()` 保留原接口，`dispatch_hour_with_limits()` 保留 dataclass 兼容接口，`dispatch_hour_values_with_limits()` 返回原始 values 供 `run_single_scenario()` 热路径直接消费；`run_single_scenario()` 在循环外预计算 BESS 功率能量限额、SOC 能量边界、并网/上网能量限额、策略枚举和曲线数组，循环内避免为每小时创建 `DispatchStep` dataclass，减少每小时重复参数解析、对象创建和 pandas Series 构造；不改变 V0.1 调度口径。
- 无储能方案已接入 NumPy 快路径。该类方案没有 SOC 滚动状态，不需要逐小时创建 dispatch 调用；summary-only 分支直接按数组计算直供、下网、上网、弃电、年上网比例 cap、站用电和电网交换限额汇总，再复用 `calculate_summary_from_values()`；保留逐小时明细时也用同一组数组构造 `HourlyEnergyLedger`，再复用 `calculate_summary()`。该优化仅影响无储能分支，不改变有储能 SOC 滚动口径。
- 批量技术仿真已在 hot path 关闭逐方案 `InputDiagnostics` 构造；单方案公开调用默认仍保留 diagnostics。保留逐小时明细的场景已把 tiny float / `-0.0` 清零从 pandas DataFrame 后处理移到 DataFrame 构造前的 numpy 数组处理，减少 `mask/_where` 开销；不改变 hourly ledger 字段或 summary 口径。
- 批量 summary-only 热路径已复用共享空 hourly ledger，避免未保留逐小时明细的每个方案都新建一个空 pandas DataFrame；公开单方案默认调用仍返回带列名的空表。
- 有储能场景已把光伏/风电出力、正负出力拆分、站用电、净可用绿电、调度负荷和逐小时电量等与 SOC 无关的数组移到循环外预计算；逐小时循环内仍保留同一套 BESS SOC 滚动和 dispatch helper，不改变 V0.1 调度口径。
- 批量技术仿真已复用 `PreparedCurveData`，同一批次只从输入 `DataFrame` 提取一次 timestamp、负荷、光伏和风电数组；每个方案复用这些数组，避免重复 DataFrame 取列和 `to_numpy()` 转换。
- 含储能批量 hot path 已跳过 `dispatch_bess_hour_values_with_limits()` 的最终防御性输出夹紧：public dispatch helper 默认仍保留 `max(..., 0.0)` 语义，批量 simulator 在已验证非负输入和预计算限额条件下传入 `clamp_outputs=False`，避免每小时重复执行一组冗余 `max()`。
- 含储能 summary-only 热路径已新增只返回数值的 `dispatch_bess_hour_summary_values_with_limits()`，不再为未保留逐小时明细的方案计算 `hour_case` 字符串；summary-only 也不再逐小时计算/夹紧 `soc_start` / `soc_end`，只在结束时计算一次 `final_soc`。
- 含储能 summary-only 热路径已把 BESS helper 内部热点 `max()` / `min()` 改为等价条件比较，并把最大下网/上网功率的循环内 `max()` 改为先跟踪最大电量、结束后一次性换算功率，减少每小时 Python 函数调用。
- 含储能 summary-only 热路径已进一步内联为 `_run_bess_summary_only()` 累加器，不再每小时调用 tuple-return dispatch helper；完整逐小时明细路径仍使用 `dispatch_bess_hour_values_with_limits()` 生成 `hour_case`、SOC 和完整 ledger。

## 2. 新增基准脚本

新增脚本：

```powershell
python scripts\benchmark_internal_pilot_performance.py
```

默认会用合成 8760 小时曲线和中等方案池运行：

- 技术仿真完整逐小时明细保留；
- 技术仿真 summary-first；
- 经济性 summary-only、无年度现金流常驻。

可用于快速小样本检查：

```powershell
python scripts\benchmark_internal_pilot_performance.py --hours 168 --pv-count 4 --wind-count 4 --bess-power-count 2 --durations 0,2 --skip-full-retention
```

可用于机器可读输出：

```powershell
python scripts\benchmark_internal_pilot_performance.py --json
```

注意：该脚本是决策辅助，不是固定性能门槛测试。不同电脑、Python 版本、进程数和后台负载都会影响结果。后续做性能优化时，应把优化前后的命令、参数、耗时和峰值内存记录到 `notes/PRODUCT_POLISH_LOG.md`。

## 3. 优化路线

### Phase P1：基准与限流

目标：让用户在点击“开始测算”前知道任务规模，避免无提示地跑成千上万个方案。

要做：

- 在 UI 中继续保留方案数预估；
- 增加大任务确认和预计耗时提示；（已完成第一版：粗略耗时区间 + 大批量确认）
- 增加单次方案数上限的环境变量或后台配置；（已完成第一版：`GREEN_DIRECT_MAX_SCENARIOS_PER_RUN`）
- 方案数预估和硬上限判断避免先物化完整方案池；（已完成第二版：轴计数估算 + 超限前置拒绝）
- 记录 benchmark 样本：方案数、小时数、是否保留明细、并行 worker、耗时、内存。

验收：

- 小规模行为不变；
- 超阈值任务给出清晰提示；
- 仍能通过现有 `pytest` 回归。

### Phase P2：汇总优先成为默认大任务路径

目标：大方案池只为推荐、图表、报告所需方案生成逐小时明细。

要做：

- 大方案池默认 `retain_hourly_details=False`；
- 推荐组合确定后，为代表方案生成或加载逐小时明细；
- 把按需补算得到的逐小时明细写入项目级 artifact，而不只存在当前 session；
- 价格曲线经济性在缺少全量明细时继续禁止或明确降级。

验收：

- 未保留明细的方案仍有完整技术 summary；
- 选中方案补算明细与全量保留模式结果一致；
- 历史 summary-only 结果在有受控输入 artifact 时可跨会话补算。

### Phase P3：后台 Job 与进度/取消

目标：多人试用时，长任务不阻塞前台会话。

已完成第一步：

- 欢迎页“项目任务与结果”面板已可筛出当前项目 `queued` / `running` 活动任务，并提供最小取消入口；取消动作仍走 `PilotAccessService.cancel_job()` 权限校验和审计。
- 欢迎页已新增“任务状态明细”，可在项目内查看任务状态、进度、worker、最后 heartbeat、stale 标记和错误说明。
- `Job` 已记录 `worker_id` / `last_heartbeat_at`，`LocalJobStore` 和 `pilot-admin fail-stale-jobs` 可把超时 running 任务元数据标记为 failed；这只是运维恢复入口，不是正式 worker 级中断。
- `pilot-admin list-jobs` 已可按项目和状态列出任务，并可标记 running 任务是否超过 heartbeat 阈值，作为完整任务状态页前的运维可见性入口。
- `LocalJobStore.claim_next_queued_job()`、`PilotAccessService.claim_next_job_for_worker()` 和 `pilot-admin claim-next-job` 已提供第一版 worker 认领原语，可按任务类型认领 queued job，写入 worker/heartbeat，并在服务层跳过归档项目；`PilotAccessService.update_worker_job_progress()` 和 `pilot-admin heartbeat-job` 可刷新已认领 running job 的 heartbeat/进度；`succeed_worker_job()` / `fail_worker_job()` 与 `complete-worker-job` / `fail-worker-job` 可写入成功/失败终态和 `COMPLETE_JOB` 审计。

要做：

- 技术仿真、经济性测算、图表/报告导出统一登记为 `Job`；
- 前台提交任务、轮询真实 worker 状态、定期 heartbeat、显示进度、支持 worker 级取消；技术仿真 worker 应优先按方案块而不是单方案调度，延续当前 `run_batch()` 的分块并行思路；
- worker 从 `ResultStore`/输入 artifact 读取数据，写回 summary、明细和导出文件；
- 失败状态写入脱敏错误和审计日志。

验收：

- 页面刷新后仍能看到任务状态；
- 用户只能看到有权限项目的任务；
- 取消任务不会留下可误用的半成品结果。

### Phase P4：经济性批量化

目标：经济性 V1 在大方案池下不成为第二个主要瓶颈。

要做：

- 继续把固定年限、折现因子、投资、运维、折旧等计算批量化；
- 未保留年度现金流的方案不构造年度现金流表；（已完成第二版：批量 summary-only 也跳过逐年 row dict 构造并复用内部空表哨兵）
- 将其他经营收入年度表、电源侧固定收入/成本和基础折旧预处理为可复用上下文；（已完成第一版）
- 将电源侧和同一主体批量评价的全方案共享参数预处理成批量上下文，避免每个方案重复解析同一组经济参数；（已完成第一版）
- 保留 FIRR 精确口径，但对常规单符号变化现金流使用快速路径；
- 对储能更换导致的临时小额现金流下凹使用 bisection 快路径，避免大批量方案反复扫描完整候选利率网格；（已完成第一版）
- 对仍需 fallback 的多根候选扫描使用 NumPy 批量 NPV 和符号穿越区间识别，避免逐候选利率执行 Python NPV 热循环；（已完成第一版）
- 推荐排序只依赖经济性 summary；
- UI 已在大方案池下只为前 N 个方案保留完整年度现金流；固定价/网页组价结果已支持用户指定方案按需后台补年度现金流。后续应补逐时价格曲线模式的价格曲线 artifact、全局任务通知和正式队列。

验收：

- `tests/test_economy_v1.py`、`tests/test_single_entity_economy.py` 保持通过；
- 同一组输入下经济性 summary 与优化前一致；
- 年度现金流保留策略不影响推荐排序。
- 后续可继续把更多 DataFrame/NumPy 批量计算和价格曲线聚合放进共享上下文，避免每个方案重复解析同一组输入。
- 已减少单方案热路径里的 `DispatchStep` 对象创建：`dispatch_hour_values_with_limits()` 与 `dispatch_hour_with_limits()` 保持同一计算逻辑，现有 golden/批量一致性测试用于证明口径不变；已将批量 runner 不消费的逐方案 diagnostics 变为可跳过，并把 hourly numeric cleanup 前移到 numpy 数组；无储能 summary-only 和无储能 retained hourly detail 场景已走 NumPy 快路径；有储能场景已把与 SOC 无关的曲线派生量移出逐小时循环，批量入口已复用同一份曲线数组；有储能热路径新增 `dispatch_bess_hour_values_with_limits()`，绕过通用 `has_bess` 分支，并在未配置电网交换功率限制时跳过 `min(..., inf)` 型计算；批量 hot path 还会跳过 public helper 的最终防御性输出夹紧，减少每小时冗余 `max()` 调用；含储能 summary-only 场景已内联为 `_run_bess_summary_only()` 累加器，不生成 `hour_case`，不逐小时调用 tuple-return helper，只在循环结束计算一次 `final_soc`。后续可继续评估 dispatch 内核编译化或后台 Job 化。

## 4. 不做的事

当前阶段不要为了性能：

- 改 V0.1 储能调度口径；
- 用近似模型替代逐小时 dispatch；
- 让储能从电网充电或放电上网；
- 把价格曲线经济性套到缺少逐小时明细的方案上；
- 一次性重写为新的计算引擎或微服务。

## 5. 给 Claude Code 的性能专项提示词

```text
请做一次“方案遍历与经济性测算性能专项”。

目标是支持内部 10-20 人试用中的大方案池测算，不改变 V0.1 技术调度口径、经济性 V1 现金流口径或推荐 V1 排序口径。

请先阅读 docs/PERFORMANCE_OPTIMIZATION_PLAN.md、src/green_direct/batch/batch_runner.py、src/green_direct/core/single_scenario_simulator.py、src/green_direct/services/study_runner.py、src/green_direct/economy/economic_evaluator.py、src/green_direct/economy/single_entity_evaluator.py，以及相关测试。

先运行：
python scripts/benchmark_internal_pilot_performance.py --hours 168 --pv-count 4 --wind-count 4 --bess-power-count 2 --durations 0,2 --skip-full-retention --json
python -m pytest tests/test_batch_runner.py tests/test_study_runner.py tests/test_economy_v1.py tests/test_single_entity_economy.py -q

然后审查并优先处理：
1. 大方案池是否默认走 summary-first；
2. 按需逐小时明细是否与全量保留结果一致；
3. 并行仿真是否保持 scenario_id、warning、error、进度和结果顺序稳定；
4. 经济性测算是否仍为每个方案常驻年度现金流；
5. UI 的方案数硬上限默认值是否合适，是否还需要耗时提示、取消/后台 Job 的下一步切片。

允许直接修改不改变口径的性能与内存问题；任何可能改变技术 dispatch、经济性现金流或推荐排序的改动必须先说明，并同步测试和文档。

完成后请给出优化前后 benchmark 命令和结果、修改文件、测试命令、未解决瓶颈和下一步建议。
```
