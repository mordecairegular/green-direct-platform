# 绿电直连风光储方案策划与测算平台

> 当前项目已从“V0.1 风光储批量技术测算工具”升级规划为“绿电直连 / 微电网项目方案策划与推荐平台”。V0.1 技术测算仍作为稳定基线保留，后续开发请优先阅读 `AGENTS.md`、`CLAUDE.md`、`notes/HANDOFF_FOR_NEW_MACHINE.md`、`notes/PRODUCT_POLISH_LOG.md` 和 `docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`。

本项目当前以并网型风光储技术测算为底座，逐步增加输入诊断、经济性评价、代表方案推荐、图表和报告能力。

## 当前能力

当前代码已经具备：

1. 读取负荷、光伏、风电逐时曲线；
2. 支持 8760 小时普通年与 8784 小时闰年；
3. 支持风电、光伏、储能多方案批量测算；
4. 支持储能 SOC 逐小时滚动计算；
5. 输出每个方案的自发自用、上网、弃电、购电、储能循环等指标；
6. 自动判断是否满足政策约束；
7. 提供 Streamlit 交互界面和结果导出；
8. 提供经济性评价 V1：年度现金流、FNPV、FIRR、静态/动态回收期；
9. 提供围绕代表方案和用户加入方案的“方案图谱”展示；
10. 提供内部试用后台的本地账号、认证、权限、任务和结果存储服务骨架，以及 `pilot-admin` 命令行账号管理入口。

## 重要文档

长期有效的开发规则和项目记忆：

- `AGENTS.md`
- `CLAUDE.md`
- `notes/HANDOFF_FOR_NEW_MACHINE.md`
- `notes/PRODUCT_POLISH_LOG.md`
- `docs/SOFTWARE_OVERVIEW_AND_INTERFACE.md`

V0.1 技术基线文档：

- `PRD.md`
- `ALGORITHM_SPEC.md`
- `DATA_SCHEMA.md`
- `OUTPUT_SCHEMA.md`
- `TEST_CASES.md`
- `UI_SPEC.md`

经济性 V1 口径：

- `docs/references/economic_evaluation/00_README_使用说明.md`
- `docs/references/economic_evaluation/经济性评价V1计算口径_合并版.md`

架构重定向材料：

- `notes/architecture_reframe_20260519/`

## 最小运行目标

项目应至少支持：

```bash
pip install -r requirements.txt
pytest
streamlit run src/green_direct/ui/app.py
```

内部试用账号 bootstrap 示例：

```bash
export GREEN_DIRECT_ADMIN_PASSWORD='change-me-before-use'
python -m green_direct.cli pilot-admin bootstrap \
  --store-dir .runtime/pilot_store \
  --user-id admin \
  --login-name admin@example.local \
  --display-name Admin \
  --password-env GREEN_DIRECT_ADMIN_PASSWORD
```

该 CLI 是管理员页面完成前的本地运维入口，不代表正式公网 SaaS 身份系统已完成。
