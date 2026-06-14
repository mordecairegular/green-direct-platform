# 当前图表模块逻辑说明报告

日期：2026-06-02  
适用范围：`src/green_direct/visualization/` 当前代码状态  
目的：说明当前图表有哪些、怎么选方案和代表日、曲线怎么画、哪些地方忠于原始结果、哪些地方只是展示近似。

## 1. 一句话结论

当前图表模块总体是“只读展示层”：主要读取技术仿真的 `summary` 和 `hourly_detail`，不重新计算储能调度、上网、弃电或经济性。

但有三点需要特别注意：

1. “春季 / 夏季 / 秋季 / 冬季典型日”已改为季节中心日法：在该季完整 24 小时日期中，按逐小时曲线特征选离季节平均曲线最近的真实日期；图表主标题不嵌入日期，选中日期写入说明和导出 meta。
2. “年度能源流向 Sankey”中的光伏、风电去向分摊按全年光伏/风电发电占比近似拆分，不是逐小时能源来源追踪。
3. 当前 Streamlit 推荐图表页已优先消费正式 `RecommendationPortfolio`，图表默认围绕推荐组合和用户手动加入方案；只有推荐组合缺失或没有有效 `scenario_id` 时，才回退到图表模块内部的技术代表方案临时逻辑。
4. 2026-06-10 起，网页端 24H 运行策略图和 HTML/PNG 图表包复用同一套构图和能源色板；图表包补充四季典型日、关键运行日、全年 8760/8784 曲线，季节典型日文件名不再嵌入日期。

## 2. 图表模块读取的数据

当前图表主要有两类输入：

| 数据 | 来源 | 用途 |
|---|---|---|
| `summary` | 批量技术仿真年度汇总 | 方案卡片、政策指标、容量对比、经济性关联、年度电量流向 |
| `hourly_detail` | 单方案逐小时明细 | 典型日曲线、关键日曲线、全年 8760/8784 曲线、热力图、SOC、储能和电网功率 |

底层事实表来自 `run_single_scenario()` 输出的 `ScenarioResult.hourly_detail`。代码中已经明确写明：政策、经济、图表、报告层应读取这些字段，不应重新计算核心调度、SOC、电网交互、上网或弃电逻辑。

批量运行时，`BatchResult.hourly_details` 保存 `scenario_id -> hourly_detail`，当前图表页就是按 `scenario_id` 取出对应逐小时明细。

## 3. 当前主界面实际展示的图表

当前 Streamlit 推荐分析页调用的是：

```text
src/green_direct/ui/app.py
-> render_chart_analysis()
-> src/green_direct/visualization/chart_ui.py
```

主界面分为四个页签。

### 3.1 方案总览

图表 / 组件：

- 代表方案卡片；
- 用户加入方案卡片；
- 当前方案关键指标；
- 多方案关键指标分组柱状对比图。

核心逻辑：

- 先选出系统代表方案和用户加入方案；
- 当前图表始终围绕一个 `active_id`；
- 分组柱状图最多展示前 5 个已选方案；
- 每个方案的图例会显示 `scenario_id` 和风光储容量配置；
- 对比图四个维度为：
  - `green_load_rate`：绿电占比；
  - `self_use_rate`：自发自用率；
  - `1 - curtail_rate`：低弃电，越大越好；
  - `1 - export_rate`：低上网，越大越好。

注意：后两个维度做了“越大越好”的展示转换，并不是直接画原始 `curtail_rate` 和 `export_rate`。

### 3.2 能量流向

图表：

1. 新能源发电构成环图；
2. 年度能源流向 Sankey 图。

取数逻辑：

- 环图直接对当前方案逐小时 `pv_generation_power`、`wind_generation_power` 求和；
- Sankey 的年度电量来自当前方案 `summary`：
  - `direct_self_use_energy`
  - `bess_charge_energy`
  - `grid_export_energy`
  - `curtail_energy`
  - `bess_discharge_to_load`
  - `bess_loss_energy`
  - `grid_import_energy`

近似逻辑：

- 光伏、风电到各去向的分摊，不是逐小时追踪出来的；
- 当前做法是先算全年光伏 / 风电发电占比，再把“直供、充储、上网、弃电”等年度去向按这个占比分摊。

可复核结论：

- Sankey 中每个去向的年度总量来自技术结果；
- 但“某一条光伏 -> 负荷”或“风电 -> 储能”的具体拆分是展示近似；
- 如果年末 SOC 与初始 SOC 不一致，Sankey 当前没有单独画出“储能年末电量变化”，储能节点可能不是严格守恒图。

### 3.3 运行时序

运行时序分为三个子页签：

1. 典型季节日；
2. 关键运行日；
3. 全年8760曲线。

#### 典型季节日怎么选

当前选择规则为“季节中心日法”。

| UI 选项 | 候选月份 |
|---|---|
| 春季 | 3、4、5 月 |
| 夏季 | 6、7、8 月 |
| 秋季 | 9、10、11 月 |
| 冬季 | 12、1、2 月 |

具体做法：

1. 把 `timestamp` 转为日期、月份和小时；
2. 按季节取对应月份内所有日期；
3. 只保留具有完整 0-23 点的真实 24 小时日期；
4. 对候选日逐小时字段构成日向量；
5. 默认使用已有字段：`load_power`、`pv_generation_power`、`wind_generation_power`、`renewable_power`、`bess_charge_power`、`bess_discharge_power`、`grid_import_power`、`grid_export_power`、`curtail_power`、`soc_end`；
6. 对这些字段做标准化，避免负荷这类大数值字段压倒 SOC、弃电等字段；
7. 计算每一天与该季平均日向量的距离；
8. 选择距离最小的真实日期；
9. 图表说明和导出 meta 中显示该日期的 `MM/DD`，图表主标题和文件名保持稳定。

如果候选季节没有完整 24 小时日期，会退回到该季节首个可用日期；如果缺少日期字段，则退回前 24 小时作为示例日。退回逻辑只影响展示选日，不会改动技术仿真结果。

重要判断：

- 这不是固定月份中位日；
- 它会同时参考负荷、风光、储能、电网、弃电和 SOC 等已有逐小时字段；
- 它选出的仍然是原始数据中的某一天，不做曲线合成；
- 图上的每个点仍来自 `hourly_detail` 原始逐小时明细。

#### 典型日曲线怎么画

当前主界面的 24 小时运行图分上下两块：

上图：

- 正向柱：
  - `pv_generation_power`：光伏可发；
  - `wind_generation_power`：风电可发；
  - `bess_discharge_power`：储能放电；
  - `grid_import_power`：电网下网。
- 负向柱：
  - `bess_charge_power`：储能充电；
  - `grid_export_power`：上网；
  - `curtail_power`：弃电。
- 折线：
  - `load_power`：负荷。

下图：

- `soc_end`：小时末 SOC。

可复核结论：

- 曲线和柱子直接来自逐小时明细，没有平滑、插值或重新调度；
- 但该图是“运行态势图”，不是严格的能量平衡堆叠图；
- 因为它把光伏、风电正发电直接画出来，同时也画储能放电、下网、充电、上网、弃电；
- 它没有展示站用电，也没有把“新能源直供负荷”单独作为供给来源。

如果要严格看“负荷由谁供给、富余去了哪里”，应直接复核 `hourly_detail` 中的负荷平衡和新能源去向字段。当前导出的 S03 图已改为网页端同款运行策略图：正向柱展示光伏/风电可发、储能放电、下网，负向柱展示储能充电、上网、弃电，下方展示 SOC。

#### 关键运行日怎么选

当前支持：

| 关键日类型 | 选择逻辑 |
|---|---|
| 最大负荷日 | 按日期汇总 `load_power`，取合计最大日期 |
| 最大弃电日 | 按日期汇总 `curtail_power`，取合计最大日期 |
| 最大下网日 | 按日期汇总 `grid_import_power`，取合计最大日期 |
| SOC 最低日 | 找全年 `soc_end` 最低的小时，取该小时所在日期 |
| SOC 最高日 | 找全年 `soc_end` 最高的小时，取该小时所在日期 |

这些关键日比“季节典型日”更可复核，因为它们都有明确排序指标。

#### 全年8760曲线怎么画

默认可选曲线：

- `load_power`：负荷；
- `renewable_power`：新能源净可用；
- `grid_import_power`：下网；
- `grid_export_power`：上网；
- `curtail_power`：弃电；
- `soc_end`：SOC。

绘制方式：

- 使用原始逐小时点，不做平滑或抽样；
- 分三行展示：供需与下网、上网与弃电、储能 SOC；
- 上网与弃电使用填充面积，SOC 单独使用百分比轴，避免所有指标挤在一个坐标系。

### 3.4 经济性分析

图表：

- 当前方案经济性指标卡；
- 多方案经济性对比图。

取数逻辑：

- 读取经济性 V1 结果表；
- 使用字段：
  - `construction_cash_outflow`
  - `fnpv`
  - `firr`
  - `static_payback_year`

可复核结论：

- 图表只读取经济性评价结果；
- 不重算年度现金流；
- 不改变技术结果。

## 4. 当前代表方案选择逻辑

推荐图表页的默认入口是正式推荐引擎 V1：

1. `src/green_direct/ui/app.py` 先调用 `build_recommendation_study()` 得到 `RecommendationPortfolio`；
2. `render_chart_analysis()` 接收该推荐组合；
3. 图表页默认方案列表按推荐组合中的 `scenario_id`、`recommendation_labels` 和 `recommendation_reason` 构造；
4. 同一个方案命中多个推荐席位时，图表标签沿用推荐组合的合并标签；
5. 用户仍可在“加入用户关注方案参与对比”中手动加入其他枚举方案，但这不改变推荐结果。

当正式推荐组合缺失、为空或没有有效 `scenario_id` 时，`chart_ui.py` 才使用内部临时代表方案逻辑兜底。兜底选择步骤：

1. 如果 `summary` 里有 `pass_policy`，优先只在 `pass_policy == True` 的方案中选；
2. 如果没有达标方案，就退回到全部方案；
3. 如果有经济性结果且包含 `fnpv`：
   - “推荐方案”按 `fnpv` 从高到低选；
   - 如果有 `green_load_rate`，作为辅助排序；
4. 如果没有经济性结果：
   - 优先按 `green_load_rate` 高；
   - 再按 `curtail_rate` 低；
   - 再按 `bess_energy` 低；
5. 再补充：
   - 高消纳备选：`green_load_rate` 最高；
   - 低弃电备选：`curtail_rate` 最低；
   - 低储能备选：`bess_energy` 最小，绿电占比更高优先；
6. 如果同一个 `scenario_id` 命中多个标签，就合并标签；
7. 最多返回 4 个代表方案。

风险判断：

- 正常推荐页路径下，图表代表方案与推荐卡片一致；
- 兜底规则只用于没有推荐结果的图表展示，不应被解释为正式推荐结论；
- 下载页的图表 HTML ZIP 中，多方案对比范围也会优先收窄为“推荐组合 + 当前报告方案”，避免把全量枚举作为默认图表对象。

## 5. 库里已有但当前主界面未全部直接使用的图表构造函数

`src/green_direct/visualization/` 下还有一批可复用图表构造函数。它们大多返回统一 `ChartResult`，包含图对象、图表数据、使用字段和口径说明。

### 5.1 单方案图表

| ID | 函数 | 图表 | 数据来源 | 逻辑 |
|---|---|---|---|---|
| S01 | `build_indicator_cards` | 方案指标卡 | `summary` | 取年度汇总字段做表格展示 |
| S02 | `build_policy_bar_chart` | 政策指标达标对比图 | `summary` | 实际值用柱，政策阈值用每个指标上的水平阈值线 |
| S03 | `build_daily_balance_chart` | 24H 源网荷储运行策略图 | `hourly_detail` | 按选定日期画网页端同款正负柱运行策略和 SOC |
| S04 | `build_heatmap_chart` | 年度热力图 | `hourly_detail` | 透视为 `小时 × 年内日序`，默认均值聚合 |
| S05 | `build_monthly_load_source_chart` | 月度用户用电来源堆叠图 | `hourly_detail` | 按月求和新能源直供、储能放电、下网 |
| S06 | `build_monthly_renewable_flow_chart` | 月度新能源去向堆叠图 | `hourly_detail` | 按月求和直供、充储、上网、弃电、站用电 |
| S07 | `build_soc_chart` | SOC 时序图 | `hourly_detail` | 直接画 `soc_end` |
| S08 | `build_battery_power_chart` | 储能充放电功率图 | `hourly_detail` | 放电为正，充电取负 |
| S09 | `build_grid_exchange_chart` | 电网交换功率图 | `hourly_detail` | 图中净交换显式按 `grid_export_power - grid_import_power`；原始 `grid_exchange_power` 保留在导出数据中复核 |
| S10 | `build_full_year_operation_chart` | 全年 8760/8784 小时运行曲线 | `hourly_detail` | 三行分面展示供需与下网、上网与弃电、SOC |
| S11 | `build_abnormal_day_table` | 异常日排行榜 | `hourly_detail` | 按日汇总后找最大负荷、最大下网、最大上网、最大弃电、SOC 极值日 |

### 5.2 多方案图表

| ID | 函数 | 图表 | 数据来源 | 逻辑 |
|---|---|---|---|---|
| M01 | `build_multi_policy_comparison` | 多方案政策指标对比图 | `summary` | 多方案自发自用率、绿电占比、上网比例分组柱状图 |
| M02 | `build_multi_capacity_comparison` | 多方案容量配置对比图 | `summary` | 光伏、风电、储能功率、储能容量分组柱状图 |
| M03 | `build_multi_renewable_flow_comparison` | 多方案新能源去向对比图 | `summary` | 自发自用、上网、弃电、储能损耗柱状图 |
| M05 | `build_curtailment_vs_self_consumption_scatter` | 弃电率 vs 自发自用率散点图 | `summary` | 横轴自发自用率，纵轴弃电率，颜色绿电占比，点大小储能容量；至少 2 个方案才生成，单方案时跳过 |
| M06 | `build_multi_battery_cycles_comparison` | 储能等效循环次数对比图 | `summary` | 比较 `annual_equivalent_cycles` |

### 5.3 导出辅助

| 函数 | 作用 |
|---|---|
| `chart_to_html_bytes` | 导出交互式 HTML |
| `chart_to_excel_bytes` | 导出图表数据、元数据和警告 |
| `chart_to_meta_markdown` | 导出图表口径说明 |
| `chart_to_png_bytes` | 按 A4 纵向 Word 正文宽度导出报告版 PNG；复制 Plotly figure 后调整宽高，不污染网页展示 |
| `charts_to_png_bytes_batch` | 优先用 Plotly `write_images()` 批量导出多张 PNG，比逐张 `to_image()` 更快；失败时 UI 侧会回退逐张导出 |
| `try_chart_to_png_bytes` | 尝试导出 PNG，依赖 kaleido 和可用 Chrome / Chromium 环境 |

当前下载页同时提供两类图表包：

- 交互式 HTML ZIP：保留 Plotly 交互能力，适合网页复核、悬停查看数据和审查图表口径；
- Word 友好 PNG ZIP：使用同一批图表清单，生成适合插入 docx 的静态图片、每图 meta、`chart_manifest.csv` 和 `README.md`。

PNG 包默认面向 A4 纵向 Word 页面，建议在 Word 中按 16 cm 宽度插入。导出画布宽度为 1800px；24H 典型日和关键运行日图高度 1300px，全年 / SOC / 电网交换 / 热力图高度 1000px，月度 / 多方案图高度 900px。若缺少 `plotly>=6.1`、`kaleido>=1.0` 或可用 Chrome / Chromium，PNG 会在 UI 和 `warnings.txt` 中提示失败原因，HTML ZIP 不受影响。

2026-06-10 后，Streamlit 06 页的 PNG ZIP 生成是后台任务。用户点击生成后可以切换到其他页面继续操作，返回下载页时自动轮询并读取结果；下载按钮使用 `on_click="ignore"`，减少下载动作触发额外页面重跑。

## 6. 忠于原始数据的程度

### 6.1 比较可靠的部分

以下图表基本忠于技术结果：

- 全年 8760/8784 曲线；
- SOC 时序；
- 储能充放电功率图；
- 电网交换功率图；
- 关键运行日；
- 月度求和图；
- 多方案容量、政策、指标对比；
- 经济性对比图。

原因：

- 它们直接读取 `summary` 或 `hourly_detail`；
- 不重新调度；
- 不平滑；
- 不插值；
- 不重新定义政策分母。

### 6.2 需要谨慎解读的部分

| 图表 / 逻辑 | 风险 | 建议解读 |
|---|---|---|
| 季节典型日 | 是最接近季节平均曲线的真实日，但仍代表不了极端日 | 适合看常规运行形态；极端复核应看关键运行日 |
| 24H 运行策略图 | 正负柱展示运行态势，不是严格平衡堆叠；网页、HTML ZIP 和 PNG ZIP 共用同一套图形口径 | 看趋势可以，看严格能量平衡应查 hourly_detail |
| 年度 Sankey 光伏/风电分摊 | 按全年发电占比分摊，不是逐小时溯源 | 只看总量和大方向，不要解读为真实来源追踪 |
| 年度 Sankey 储能节点 | 没有单独展示年末 SOC 变化 | 年初年末 SOC 不同则不完全守恒 |
| `chart_ui.py` 缺字段处理 | 部分曲线缺字段时会画 0 | 当前标准 `BatchResult` 字段完整时影响不大；外部数据接入时需注意 |
| 月度求和图 | 直接对功率字段求和，隐含 `dt_hours = 1` | 当前 8760/8784 小时口径成立；未来 15 分钟需乘 `dt_hours` |
| S02 政策阈值 | 默认阈值 60% / 30% / 20% | 如果用户修改政策阈值，调用方必须显式传入 thresholds |

## 7. 手工复核建议

### 7.1 复核春季典型日

春季候选日来自 3、4、5 月所有完整 24 小时日期。复核方法：

1. 找当前方案 `scenario_id`；
2. 从 `batch_result.hourly_details[scenario_id]` 取逐小时表；
3. 过滤 `timestamp.dt.month.isin([3, 4, 5])`；
4. 按日期分组，只保留 0-23 点完整的日期；
5. 取参与典型日选择的字段，按列标准化；
6. 计算每一天与春季平均日向量的均方距离；
7. 距离最小的日期应等于图表说明和导出 meta 中记录的 MM/DD；
8. 检查图上 24 个点是否等于该日期的逐小时字段。

### 7.2 复核 24H 曲线

对选中日期，直接检查这些列：

```text
timestamp
load_power
pv_generation_power
wind_generation_power
bess_discharge_power
grid_import_power
bess_charge_power
grid_export_power
curtail_power
soc_end
```

图上不应出现这些列之外的重新计算值。

### 7.3 复核严格负荷平衡

当前基线下，可对每小时检查：

```text
load_power
≈ direct_self_use_power
  + bess_discharge_power
  + grid_import_power
```

如果存在风光负值站用电或下网交换功率限制，还应结合：

```text
station_use_power
exchange_import_shortfall_power
```

以及核心逐小时调度文档中的 `dispatch_load_power` 口径复核。

### 7.4 复核新能源去向

当前简化口径下可检查：

```text
renewable_power
≈ direct_self_use_power
  + bess_charge_power
  + grid_export_power
  + curtail_power
```

年度汇总可检查：

```text
self_use_energy
= direct_self_use_energy + bess_discharge_to_load
```

## 8. 测试覆盖现状

当前图表相关测试覆盖了：

- 字段别名适配；
- 时间字段派生；
- 净交换功率派生；
- 最大负荷日选择；
- 季节中心日法会选中离季节平均曲线最近的真实日期，并返回 MM/DD；导出文件名不嵌入日期；
- 缺字段时返回 warning 而不是崩溃；
- 单方案图表 smoke test；
- 多方案图表 smoke test；
- 8760 / 8784 热力图。

建议复核命令：

```powershell
python -m pytest tests/test_chart_data.py tests/test_chart_contracts.py tests/test_visualization_smoke.py
```

## 9. 后续改进建议

建议优先级如下：

1. 为季节中心日法增加可下载的选日过程明细，例如每个候选日的距离得分和参与字段，方便报告审计。
2. 为 24H 运行图增加“严格平衡视图”，默认展示 `direct_self_use_power + bess_discharge_power + grid_import_power` 与负荷，而把光伏/风电可发、上网、弃电放到第二层。
3. Sankey 如需用于正式报告，应增加口径提示或改成不拆 PV/Wind 来源的年度总流向；如果要真实拆源，需要逐小时来源追踪字段。
4. 所有聚合图为未来 15 分钟数据预留 `dt_hours`，不要长期默认“功率求和 = 电量”。
5. 主界面缺字段时不要静默补 0，至少显示提示，避免外部数据接入时把“缺字段”误读为“该项为 0”。
