# UI Flow Capture Notes

审计日期：2026-06-06

审计对象：`streamlit run src/green_direct/ui/app.py`

本轮只读运行当前 Streamlit 应用，未修改底层计算、经济性、推荐排序或数据结构。Codex in-app Browser 在当前环境中未能启动，截图改用本地 Chromium/Playwright 作为取证 fallback；截图渲染正常，但自动化接口读取中文文本时存在编码噪声，因此审计判断以截图和页面行为为准。

## Runtime

- 本地地址：`http://127.0.0.1:8503`
- Streamlit 标题：绿电直连风光储方案策划平台
- 服务日志：
  - `evidence/streamlit_8503.out.log`
  - `evidence/streamlit_8503.err.log`
- 自动化辅助记录：
  - `evidence/00-current-debug-body.txt`
  - `evidence/19-economy-button-map.json`
  - `evidence/26-economy-click-result.json`

## Main Evidence Screenshots

| 文件 | 页面 / 状态 | 主要证据 |
|---|---|---|
| `screenshots/01-welcome.png` | 欢迎页初始态 | 六页工作流、顶部状态条、左侧状态卡已成型。 |
| `screenshots/02-simulation-initial.png` | 方案仿真初始态 | 输入、候选方案池、政策约束分区已存在；空状态和输入诊断仍偏弱。 |
| `screenshots/03-economy-initial.png` | 经济性测算未满足前置 | 前置依赖提示清楚，但页面留白过大。 |
| `screenshots/04-recommendation-initial.png` | 方案推荐未满足前置 | 前置依赖提示清楚，但未解释“为什么需要经济性”。 |
| `screenshots/05-chart-overview-initial.png` | 图表概览未满足前置 | 图表页被经济性前置锁住，复核任务尚不独立。 |
| `screenshots/06-export-initial.png` | 下载报告未满足前置 | 入口空状态清楚，但可交付物结构未预告。 |
| `screenshots/14-flow-simulation-after-demo.png` | Demo 方案仿真完成 | Demo 生成 27 个方案、22 个达标；左侧状态和顶部状态同步。 |
| `screenshots/15-flow-economy-before-run.png` | 经济性参数工作台 | 参数过多且默认同屏密度高，执行按钮在首屏下方。 |
| `screenshots/16-flow-recommendation-before-economy.png` | 推荐页等待经济性 | 推荐页依赖经济结果，当前状态提示可读。 |
| `screenshots/18-flow-export-before-economy.png` | 导出页仿真后 | 可选择默认方案并导出技术数据，经济和推荐交付物未就绪。 |
| `screenshots/26-economy-after-run.png` | 经济性 V1 完成 | 状态条显示经济、推荐、图表可查看；经济页仍停留在参数工作台顶部。 |
| `screenshots/27-recommendation-after-economy.png` | 推荐结果页 | 三张推荐卡可读，已弱化全量枚举表；推荐理由被截断。 |
| `screenshots/28-chart-after-economy.png` | 图表概览页 | 默认围绕推荐组合展示指标和容量对比，方向正确。 |
| `screenshots/29-export-after-economy.png` | 导出页完成态 | 技术数据、图表包、经济报告分区集中，默认报告方案为 `S0010`。 |
| `screenshots/30-mobile-welcome.png` | 窄屏欢迎页 | 左侧导航遮挡主内容，顶部状态条和卡片被截断。 |
| `screenshots/31-mobile-simulation.png` | 窄屏方案仿真 | 仍停留在被遮挡状态，移动端不可作为正式验收目标。 |

## Flow Result

主流程可跑通：

```text
欢迎页
-> 方案仿真 Demo
-> 经济性测算 V1
-> 方案推荐
-> 图表概览
-> 下载报告
```

本轮发现的流程限制：

- 经济性测算按钮不在首屏，用户要滚动到参数区底部才会发现执行动作。
- 方案推荐和图表概览在经济性未完成时只显示前置提示；提示足够清楚，但没有给出下一步会产生哪些结果。
- 图表页完成态已经围绕推荐组合，而不是全量枚举表，方向符合当前产品定位。
- 窄屏布局不通过：侧边栏覆盖内容，主要文本和卡片被截断。
