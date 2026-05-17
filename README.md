# 绿电直连风光储多方案批量测算软件开发资料包

本资料包用于指导 Claude Code / Codex 在 VS Code 环境中分阶段开发一个“绿电直连风光储多方案批量测算模块”。

## 当前目标

开发一个 V0.1 初版软件，具备：

1. 读取负荷、光伏、风电逐时曲线；
2. 支持 8760 小时普通年与 8784 小时闰年；
3. 支持风电、光伏、储能多方案批量测算；
4. 支持储能 SOC 逐小时滚动计算；
5. 输出每个方案的自发自用、上网、弃电、购电、储能循环等指标；
6. 自动判断是否满足政策约束；
7. 具备一个初步 Streamlit 交互界面；
8. 预留后续经济性评价模块接口，但当前版本不实现经济性计算。

## 建议开发方式

不要一次性要求 AI 开发完整软件。请按 prompts/ 文件夹内的阶段提示词逐步执行。

推荐顺序：

1. prompts/00_MASTER_START.md
2. prompts/01_CREATE_PROJECT_STRUCTURE.md
3. prompts/02_DATA_IO_AND_VALIDATION.md
4. prompts/03_SINGLE_SCENARIO_SIMULATOR.md
5. prompts/04_BATCH_SCENARIO_RUNNER.md
6. prompts/05_EXPORT_RESULTS.md
7. prompts/06_STREAMLIT_UI.md
8. prompts/07_FINAL_REVIEW_AND_TEST.md
9. prompts/08_OPTIONAL_EXE_PACKAGING.md

## 核心文档说明

- PRD.md：产品需求边界
- ALGORITHM_SPEC.md：逐时能量平衡与储能调度算法
- DATA_SCHEMA.md：输入数据格式
- OUTPUT_SCHEMA.md：输出结果格式
- TEST_CASES.md：必须通过的测试用例
- UI_SPEC.md：初步交互界面设计
- ECONOMY_EXTENSION_SPEC.md：未来经济性评价预留接口
- CLAUDE.md：给 Claude Code 的项目指令
- AGENTS.md：给 Codex 等 coding agent 的项目指令
- ROADMAP.md：版本路线图
- ACCEPTANCE_CHECKLIST.md：验收清单

## 最小运行目标

开发完成后，项目应至少支持：

```bash
pip install -r requirements.txt
pytest
streamlit run src/green_direct/ui/app.py
```
