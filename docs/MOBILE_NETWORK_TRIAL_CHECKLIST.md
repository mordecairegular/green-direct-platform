# 同事移动网络试用清单

日期：2026-06-16

目标：让内部同事不在同一局域网、只用手机或移动网络，也能访问并试用绿电直连测算工具。

## 1. 推荐路径

```text
GitHub private repository
  -> Render Blueprint 部署 Docker 应用
  -> Render persistent disk 保存 /data/pilot_store
  -> Cloudflare DNS / HTTPS / Access
  -> 同事通过手机浏览器访问域名
  -> 应用内账号登录
```

不要把当前项目直接导入 Vercel 作为主机。Vercel 的 GitHub Import 适合 Next.js/静态站/serverless API；当前工具是 Streamlit 长进程和本地 pilot store，更适合容器托管。

## 2. 发布前准备

- GitHub 私有仓库已创建；
- 当前分支已推送；
- 仓库包含 `Dockerfile`、`render.yaml`、`requirements-runtime.txt`；
- `.dockerignore` 已排除 `.runtime/`、日志、输出目录、历史归档、测试目录、docs/notes 等运行镜像不需要的内容；
- 本地已运行 `python scripts\preflight_internal_pilot_deploy.py --run-smoke`，确认部署配置和服务器口径健康检查都通过；
- Render 账户可访问该 GitHub 仓库；
- Cloudflare 已接管或可管理试用域名；
- 决定一个内测域名，例如 `green-direct.example.com`；
- 准备第一批同事邮箱名单；
- 准备平台管理员一次性强密码。

## 3. Render 部署

1. 在 Render 选择 Blueprint / Import Git Repository。
2. 选择 GitHub 私有仓库。
3. 确认 Render 读取根目录 `render.yaml`。
4. 确认服务类型为 Web Service，runtime 为 Docker。
5. 确认 persistent disk：
   - mount path: `/data`
   - app store: `/data/pilot_store`
6. 部署完成后，访问 Render 默认域名。
7. 若显示应用登录页，说明公网入口已通。

## 4. 初始化管理员

在 Render Shell 或一次性命令环境中执行：

```bash
GREEN_DIRECT_ADMIN_PASSWORD='replace-with-one-time-password' \
python -m green_direct.cli pilot-admin bootstrap \
  --store-dir /data/pilot_store \
  --user-id admin \
  --login-name admin@example.local \
  --display-name "平台管理员" \
  --password-env GREEN_DIRECT_ADMIN_PASSWORD
```

随后登录应用，立刻重置管理员密码，并创建内测用户。

建议第一批账号：

- 1 个平台管理员账号；
- 1 个可导出测试账号；
- 1 个不可导出测试账号；
- 3-5 个真实同事账号，先小范围试。

## 5. Cloudflare Access

1. 在 Render 添加自定义域名。
2. 在 Cloudflare DNS 添加 CNAME。
3. 开启 HTTPS。
4. 在 Cloudflare Zero Trust Access 创建 self-hosted application：
   - 域名：试用域名；
   - 策略：只允许指定邮箱或邮箱域；
   - 禁止公开注册；
   - 可设置登录有效期，例如 24 小时或 7 天。

Cloudflare Access 是公网入口第一层门禁；应用内账号是第二层门禁。两层都保留。

## 6. 发给同事前的验收

请至少完成以下检查：

- 手机 4G/5G 网络可打开试用域名；
- 非白名单邮箱无法通过 Cloudflare Access；
- 白名单邮箱通过 Access 后仍需应用内账号登录；
- 未登录用户不能进入六步工作流；
- 可导出用户能下载自己的项目结果；
- 不可导出用户不能下载 06 页导出和 artifact；
- 普通用户看不到其他人的项目；
- 创建项目、运行小样例、重启服务后项目仍存在；
- 审计日志能看到登录、项目、下载、artifact 操作；
- `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0`；
- 数据目录不是 Git 仓库目录。
- Render/Docker 构建日志中没有上传本地 `.runtime`、输出文件、历史归档或调试日志。
- 本地 smoke、Render health check 和 Cloudflare 入口检查都通过后，再发给真实同事。

## 7. 发给同事的说明

建议说明：

```text
这是绿电直连测算工具的邀请制内测环境，仅用于前期方案测算、政策指标初判和功能反馈。

请不要上传高度敏感或正式生产数据。工具不连接、不控制任何真实电力设备，也不作为正式审批、接入批复、交易结算或投资决策依据。

首次访问需要先通过 Cloudflare 邮箱验证，再使用管理员分配的工具账号登录。
```

## 8. 发现问题时记录

同事反馈问题时，请至少记录：

- 用户账号；
- 项目名称；
- 大致时间；
- 手机/电脑；
- 浏览器；
- 操作到第几步；
- 错误提示截图；
- 是否可复现；
- 是否涉及上传文件或导出文件。

不要让同事通过聊天工具发送原始敏感曲线文件。需要排查时，由管理员在项目审计和 artifact 元数据中定位。
