# 02_DATA_IO_AND_VALIDATION.md

请开始第二阶段开发：数据读取与校验。

请实现：

1. CSV 编码自动识别，至少支持 UTF-8、UTF-8-SIG、GBK、GB18030；
2. 读取负荷、光伏、风电三条曲线；
3. 支持用户指定时间列和数值列；
4. 校验行数为 8760 或 8784；
5. 校验三条曲线行数一致；
6. 校验三条曲线时间戳一致；
7. 校验负荷值不能小于 0；
8. 光伏/风电小负值按配置截断为 0；
9. 光伏/风电明显负值时报错；
10. 光伏/风电大于 1 时默认允许但给出 warning；
11. 编写 pytest 测试，覆盖 DATA_SCHEMA.md 的规则。

建议文件：

- src/green_direct/io/read_curves.py
- src/green_direct/io/validators.py
- src/green_direct/models/params.py
- tests/test_data_validation.py

完成后：

1. 运行 pytest；
2. 展示测试结果；
3. 说明如何使用读取函数；
4. 不要实现储能算法；
5. 不要实现界面。
