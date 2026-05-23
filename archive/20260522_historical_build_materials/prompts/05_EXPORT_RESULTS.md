# 05_EXPORT_RESULTS.md

请开始第五阶段开发：结果导出。

要求：

1. 按 OUTPUT_SCHEMA.md 导出方案汇总 Excel；
2. 支持导出所有方案汇总；
3. 支持导出达标方案；
4. 支持导出不达标方案；
5. 支持导出配置快照；
6. 支持导出单方案逐小时明细 CSV；
7. 支持将多个逐小时明细打包为 ZIP；
8. 输出文件名带时间戳；
9. 编写导出测试。

建议文件：

- src/green_direct/export/excel_exporter.py
- src/green_direct/export/csv_exporter.py
- tests/test_export.py

完成后：

1. 运行 pytest；
2. 展示导出的文件路径；
3. 不要实现经济性。
