# 08_OPTIONAL_EXE_PACKAGING.md

可选阶段：EXE 打包。

只有在以下条件全部满足时才能执行：

1. pytest 全部通过；
2. Streamlit 界面可以正常启动；
3. 数据导入、计算、导出流程跑通；
4. REVIEW_REPORT.md 没有严重问题。

请使用 PyInstaller 或其他合适方式尝试打包。

要求：

1. 不要修改核心算法；
2. 不要为了打包删除测试；
3. 打包失败时输出原因；
4. 给出普通用户启动说明；
5. 生成 WINDOWS_USER_GUIDE.md。

注意：

Streamlit 程序打包为 EXE 可能会比较麻烦。若打包失败，可以先提供 `.bat` 启动脚本作为过渡方案。
