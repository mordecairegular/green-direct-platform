# 03_SINGLE_SCENARIO_SIMULATOR.md

请开始第三阶段开发：单方案逐时能量平衡计算。

请严格按照 ALGORITHM_SPEC.md 实现。

要求：

1. 实现单方案模拟函数 run_single_scenario；
2. 输入包括：
   - 负荷曲线；
   - 光伏标幺曲线；
   - 风电标幺曲线；
   - 光伏容量；
   - 风电容量；
   - 储能功率；
   - 储能容量；
   - 储能参数；
   - 政策参数；
3. 储能只能由富余新能源充电；
4. 储能不能从电网充电；
5. 储能不能同时充放电；
6. SOC 必须逐小时滚动；
7. 充电受功率和容量约束；
8. 放电受功率和容量约束；
9. 考虑充放电效率；
10. 输出逐小时 DataFrame；
11. 输出方案汇总对象或 dict；
12. 编写 TEST_CASES.md 中 Case 1-15 的测试。

建议文件：

- src/green_direct/core/bess_dispatch.py
- src/green_direct/core/single_scenario_simulator.py
- src/green_direct/core/metrics.py
- src/green_direct/models/scenario.py
- src/green_direct/models/results.py
- tests/test_single_scenario.py
- tests/test_bess_dispatch.py
- tests/test_metrics.py

完成后：

1. 运行 pytest；
2. 如果测试失败，先修复；
3. 输出核心函数签名；
4. 不要实现批量测算；
5. 不要实现界面；
6. 不要实现经济性。
