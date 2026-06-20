# 04_BATCH_SCENARIO_RUNNER.md

请开始第四阶段开发：多方案批量测算。

要求：

1. 根据 scenario_grid 配置自动生成方案组合；
2. 支持光伏容量范围；
3. 支持风电容量范围；
4. 支持储能功率范围；
5. 支持储能时长列表；
6. 储能容量按 E_bess = P_bess × duration 计算；
7. 支持 duration = 0 且 P_bess = 0 的无储能方案；
8. 对每个方案调用单方案模拟函数；
9. 汇总所有方案结果；
10. 如果单个方案失败，应记录错误，不应导致全部中断；
11. 方案数超过配置阈值时给出 warning；
12. 编写批量测算测试。

建议文件：

- src/green_direct/batch/scenario_generator.py
- src/green_direct/batch/batch_runner.py
- tests/test_batch_runner.py

完成后：

1. 运行 pytest；
2. 展示一个小型 2×2×2 方案批量结果；
3. 不要实现界面；
4. 不要实现经济性。
