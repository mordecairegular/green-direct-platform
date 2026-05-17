# WINDOWS_USER_GUIDE_TEMPLATE.md

## 1. 安装 Python

建议安装 Python 3.11 或 3.12。

安装时请勾选：

```text
Add Python to PATH
```

## 2. 安装依赖

在项目目录打开终端：

```bash
pip install -r requirements.txt
```

## 3. 启动软件

```bash
streamlit run src/green_direct/ui/app.py
```

## 4. 使用步骤

1. 上传负荷 CSV；
2. 上传光伏 CSV；
3. 上传风电 CSV；
4. 设置容量范围；
5. 设置储能参数；
6. 设置政策参数；
7. 点击开始测算；
8. 下载结果。

## 5. 常见问题

### 5.1 CSV 乱码

尝试将 CSV 另存为 UTF-8 或 GBK。

### 5.2 时间列识别失败

检查时间格式是否类似：

```text
2020-01-01 00:00:00
```

### 5.3 三条曲线无法对齐

检查三条曲线是否同一年、同一时间步长、同一小时数。
