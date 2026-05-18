# 便携包打包说明

## 打包目标

面向 Windows 普通用户提供一个解压即用的软件包。

用户只需要：

1. 解压 ZIP；
2. 双击 `启动绿电直连测算工具.bat`；
3. 在浏览器中使用软件。

## 打包策略

当前采用“便携包 + 内置 Python 虚拟环境”的方式，而不是单 exe。

原因：

- Streamlit、pandas、plotly 直接打成单 exe 体积大且兼容性更不稳定；
- 便携包更容易排查问题；
- 不要求用户手工安装 Python 依赖；
- 后续更新代码或文档更简单。

## 包内结构

```text
绿电直连测算工具_便携版/
├─ 启动绿电直连测算工具.bat
├─ README_先看我.txt
├─ requirements.txt
├─ pyproject.toml
├─ src/
├─ config/
├─ samples/
├─ docs/
├─ outputs/
└─ .runtime/
```

其中 `.runtime/` 为内置运行环境。

## 注意事项

- 用户不要删除 `.runtime/`、`src/`、`config/`、`samples/`。
- 使用期间不要关闭启动窗口。
- 如果公司电脑有安全软件拦截脚本运行，需要将该目录加入信任。
