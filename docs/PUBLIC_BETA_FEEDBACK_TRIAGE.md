# 公网内测反馈收集与排查清单

用途：首轮 10-20 人内部公网试用时，把同事反馈从零散聊天记录变成可复现、可审计、可分级处理的问题单。

本文不要求接入正式工单系统。第一版可直接复制模板到企业微信、飞书、邮件或表格。

## 1. 给同事的反馈模板

```text
【绿电直连工具内测反馈】

1. 账号：
2. 项目名称：
3. 发生时间：
4. 设备和网络：电脑/手机，Wi-Fi/4G/5G
5. 浏览器：
6. 操作到第几步：01/02/03/04/05/06
7. 问题类型：打不开/登录/上传/测算/经济性/推荐/图表/下载/其他
8. 页面提示或错误截图：
9. 是否能稳定复现：能/不能/未尝试
10. 复现步骤：
11. 是否涉及上传文件或导出文件：是/否
12. 期望结果：
13. 实际结果：
```

提醒同事：不要在聊天工具中发送高度敏感或正式生产曲线文件。需要排查数据问题时，由管理员通过项目、任务、artifact 元数据和审计记录定位。

## 2. 问题分级

P0：立即停止继续扩大试用

- 非白名单邮箱可绕过 Cloudflare Access；
- 未登录即可进入六步工作流；
- 普通用户可看到其他人的项目或结果；
- 不可导出用户可以下载结果；
- 审计日志没有记录登录、下载或关键项目操作；
- 上传、结果或备份数据进入 Git 仓库或公开链接；
- 服务重启后账号、项目或结果丢失。

P1：当天优先修复或绕开

- 登录、创建项目、上传曲线、Demo、技术仿真、经济性、推荐主流程中断；
- 大方案池导致 Web 进程长时间无响应；
- 后台任务 stuck，且平台管理页或 CLI 无法恢复；
- 结果保存成功但历史结果无法查看或下载；
- 图表或下载入口对首批同事造成明显误解。

P2：记录后排期

- 文案、布局、窄屏体验、提示不清晰；
- 非关键图表样式问题；
- 单个浏览器兼容性问题，且有可接受绕行方式；
- 性能不理想但不影响完成小样例。

## 3. 管理员首轮排查顺序

1. 确认反馈对应的账号、项目和发生时间；
2. 在平台管理页查看用户状态、项目成员和导出权限；
3. 在平台管理页“审计日志”按项目和动作过滤；
4. 在项目首页查看活动任务和历史结果索引；
5. 如是任务问题，查看任务状态、worker、最后 heartbeat、stale 标记和错误说明；
6. 如是下载问题，确认成员 `can_export_artifacts`；
7. 如是数据问题，只先看 artifact 元数据、文件名、大小、SHA256 和输入列配置，不让同事通过聊天工具发送原始敏感曲线；
8. 如怀疑 store 损坏，在服务器 Shell 运行 doctor。

Render Web Service Shell：

```bash
python -m green_direct.cli pilot-admin doctor \
  --store-dir /data/pilot_store \
  --json
```

本地或自有服务器：

```powershell
python -m green_direct.cli pilot-admin doctor `
  --store-dir $env:GREEN_DIRECT_PILOT_STORE_DIR `
  --json
```

## 4. 常用 CLI 只读排查

查看全局审计：

```bash
python -m green_direct.cli pilot-admin list-audit-events \
  --store-dir /data/pilot_store \
  --actor-user-id admin \
  --limit 50
```

查看某项目审计：

```bash
python -m green_direct.cli pilot-admin list-audit-events \
  --store-dir /data/pilot_store \
  --actor-user-id admin \
  --project-id project_id_here \
  --limit 100
```

查看任务：

```bash
python -m green_direct.cli pilot-admin list-jobs \
  --store-dir /data/pilot_store \
  --actor-user-id admin \
  --project-id project_id_here
```

这些命令只用于定位问题。不要把完整输出直接发给无关人员；其中可能包含项目名、账号 ID、文件名、artifact ID 或错误摘要。

## 5. 发给同事前的说明

```text
这是邀请制内测环境。请先用 Demo 或脱敏数据试用；不要上传正式生产数据或高度敏感曲线。遇到问题请按反馈模板提供账号、项目、时间、步骤、截图和是否可复现。不要在聊天工具里发送原始曲线文件。
```

## 6. 首轮反馈表字段

如果用表格记录，建议列：

- 编号；
- 日期；
- 反馈人；
- 账号；
- 项目名称；
- 页面步骤；
- 问题类型；
- 严重级别 P0/P1/P2；
- 是否可复现；
- 当前状态：新建/排查中/已绕行/已修复/暂缓；
- 负责人；
- 复现步骤；
- 处理记录；
- 相关审计时间范围；
- 相关 job id；
- 相关 artifact/result id；
- 是否涉及敏感数据。

## 7. 关闭问题前确认

- 已记录原因或无法复现结论；
- 如有修复，已说明对应提交或配置变更；
- 如是权限/安全问题，已复查相关审计记录；
- 如是数据或结果问题，没有把原始敏感曲线转发到聊天工具；
- 如影响同事继续试用，已给出绕行方式或明确暂停。
