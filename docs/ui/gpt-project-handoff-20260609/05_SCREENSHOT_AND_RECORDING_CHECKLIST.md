# Screenshot And Recording Checklist

Use this file when uploading visual evidence to ChatGPT Project. The goal is to let GPT review the actual UI flow, not only the code and product docs.

## Best Screenshot Batch

Upload these first if the file limit allows:

```text
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/01-main-long-project-launch.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/02-main-long-simulation-before-demo.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/03-main-long-simulation-after-demo.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/05-main-long-economy-after-run.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/06-main-long-recommendation.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/07-main-long-chart-overview-and-detail.png
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/08-main-long-export-center.png
```

Why these matter:

| File | What GPT should inspect |
|---|---|
| `01-main-long-project-launch.png` | Project launch/status console and six-step workbench framing |
| `02-main-long-simulation-before-demo.png` | Scenario simulation page before demo data is generated |
| `03-main-long-simulation-after-demo.png` | Scenario simulation after demo technical run, with candidate count and policy summary |
| `05-main-long-economy-after-run.png` | Economy result feedback and landed load price before/after green power |
| `06-main-long-recommendation.png` | Recommendation cards, merged labels, metrics, decision hierarchy |
| `07-main-long-chart-overview-and-detail.png` | Chart overview plus detailed chart selector and energy-flow review |
| `08-main-long-export-center.png` | Delivery/export center after economy results are available |

## Minimal Batch

If only 3-4 screenshots can be uploaded:

```text
01-main-long-project-launch.png
03-main-long-simulation-after-demo.png
05-main-long-economy-after-run.png
07-main-long-chart-overview-and-detail.png
08-main-long-export-center.png
```

## Optional Supporting Screenshots

Use these when GPT needs before/after or edge-state context:

```text
04-main-long-economy-before-run.png
09-mobile-full-project-launch.png
10-mobile-full-simulation.png
```

These are useful for:

- narrow/mobile layout issues;
- pages before economy/recommendation prerequisites are satisfied;
- narrow/mobile layout issues;
- economy page state before the V1 calculation;
- whether chart quick buttons visibly change the active detailed scenario.

## Recording Flow

If recording a short video, capture this path:

```text
01 项目启动台
-> 02 方案仿真：启用 Demo 或上传曲线，说明容量范围遍历 / 指定单方案入口
-> 03 经济测算：运行经济性 V1，展示曲线模式或固定价模式
-> 04 方案推荐：查看推荐卡和席位合并
-> 05 图表概览：点击推荐方案按钮切换详细图表
-> 06 图表下载和报告生成：查看交付包和默认报告方案
```

Recording length target: 2-4 minutes. Do not spend time scrolling every advanced parameter; GPT mainly needs the decision flow and state transitions.

## Capture Notes

- Capture at desktop width first, preferably around `1440 x 900` or wider.
- If mobile/narrow layout is part of the review, also include one narrow capture around `390 x 844`.
- When showing economy or recommendation pages, make sure a technical simulation has already run.
- When showing recommendation and chart pages, run economy first so recommendation seats and landed price metrics are available.
- Mention that this screenshot set was captured from the local Streamlit app on 2026-06-09 after running Demo technical simulation and economy V1.
- The desktop files are stitched long screenshots of the main work area, cropped to avoid repeating the fixed sidebar on every module.
