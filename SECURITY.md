# 安全说明

本文说明内部 10-20 人试用和受控公网内测 Route A 的安全边界。它不是正式安全审计报告。

## 支持范围

当前安全目标：

- 邀请制或管理员创建账号；
- 登录后才能上传、计算、查看项目；
- 项目成员隔离；
- 可导出/不可导出权限后端校验；
- 上传文件类型和大小限制；
- artifact payload 可设置过期清理；
- 关键账号、项目、任务和下载动作写入审计日志；
- 多人部署默认关闭本地 runtime snapshot。

不在当前范围：

- 商业化多租户 SaaS；
- 企业 IAM/OIDC/LDAP；
- 支付、计费、组织空间；
- EMS、SCADA、真实电力设备或生产控制网；
- 对外公开注册。

## 数据处理

当前本地 pilot store 会保存：

- 用户基本信息；
- 密码 hash 和 salt，不保存明文密码；
- 会话 token hash，不保存明文 token；
- 项目、成员、任务和结果索引；
- 技术/经济/推荐 summary artifact；
- artifact payload、hash、大小和保留策略；
- 审计日志。

上传文件当前已做后缀、大小和 hash 元数据记录；按需逐小时明细已有第一版项目级 artifact 留存和网页内加载路径。完整的原始上传文件留存、图表包和报告 artifact 闭环仍在后续路线中。

## 密码与密钥

- 不要把密码、token、cookie、证书私钥或 `.env` 提交到 Git；
- 首个管理员密码应通过环境变量传入 `pilot-admin bootstrap`；
- 密码应使用临时通道交给试用用户，并要求首次试用后尽快更换；
- 至少保留两个活跃平台管理员，避免单点锁死。

## 上传与日志

日志中不得记录：

- 完整负荷、光伏、风电或价格曲线；
- 上传文件全文；
- 明文密码、明文 token、cookie 或 session id；
- 不必要的服务器绝对路径；
- 敏感项目名称，除非该日志仅对授权管理员可见。

上传文件限制：

- 技术曲线默认只允许 CSV；
- 下网电价曲线允许 CSV/XLSX/XLSM；
- 默认单文件上限 20MB，可用 `GREEN_DIRECT_MAX_UPLOAD_MB` 调整；
- 默认单次技术仿真上限 20,000 个候选方案，可用 `GREEN_DIRECT_MAX_SCENARIOS_PER_RUN` 调整，超限时前台和 `run_batch()` 后端都会拒绝执行；
- 默认经济性测算超过 1,000 个方案时只常驻前 20 个方案年度现金流，可用 `GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD` 和 `GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT` 调整；summary、FIRR/NPV 和推荐排序仍按全量方案计算；
- 后续应补 schema 校验报告 artifact、原始输入 artifact 留存和清理。

## 部署要求

多人或公网可访问部署必须：

- 设置 `GREEN_DIRECT_ENABLE_PILOT_AUTH=1`；
- 设置 `GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0`；
- 将 `GREEN_DIRECT_PILOT_STORE_DIR` 指向仓库外受控目录或容器数据卷；
- 设置或确认 `GREEN_DIRECT_MAX_SCENARIOS_PER_RUN`，避免多人环境误提交超大同步计算；
- 设置或确认经济性年度现金流保留阈值，避免公网内测环境一次生成过多现金流文件；
- 使用 HTTPS 反向代理；
- 关闭开放注册；
- 限制服务器、容器和数据卷访问权限；
- 定期备份并演练恢复。

不得：

- 直接把 8503 暴露到公网；
- 把 pilot store 放入 Git 仓库；
- 把 `.runtime/latest_session_snapshot.pkl` 用于多人部署；
- 把本工具接入真实电力控制系统。

## 权限模型

当前项目成员角色包括：

- `admin`：项目管理和查看；
- `analyst`：提交和查看本项目任务；
- `viewer`：查看本项目任务和结果。

导出权限由 `ProjectMembership.can_export_artifacts` 独立控制。不可导出成员可以查看网页结果；网页内恢复或图表查看走 `VIEW_ARTIFACT` 审计，不授予文件下载。后端下载/导出 payload 读取和 06 页导出必须被拒绝，并写入 `DOWNLOAD_ARTIFACT` 审计。

未来 API、反向代理下载、对象存储签名 URL、图表包和报告 artifact 必须复用同一导出授权语义。

## 漏洞与风险报告

内部试用阶段发现以下问题应立即停止公网访问并排查：

- 未登录用户可进入业务工作流；
- 普通用户可看到他人项目或 artifact；
- 不可导出用户可下载结果；
- 日志出现明文密码、token 或原始曲线；
- runtime snapshot 在多人部署中恢复了旧结果；
- 服务器或容器数据卷被未授权访问。

## 已知限制

- 本地 JSON/file store 已有元数据原子写入保护，但没有数据库事务、并发锁、冲突合并和正式备份调度；
- 计算任务仍主要在 Streamlit 进程内同步执行；当前已有按需 hourly detail、固定价/网页组价 annual cashflow 的 queued job 提交入口、one-shot worker、最小 `run-worker-loop` 轮询 worker、stale running 置失败入口和 failed/canceled 任务手动克隆重试入口，尚无正式队列、自动重试策略或 worker 级取消；
- 历史 summary-only 结果可加载已有 hourly artifact；若原始 input artifact 仍可用，可同步补算或提交后台排队补算，缺少 input artifact 时不能跨会话补算逐小时明细；
- 不是正式公网 SaaS 安全架构；
- 需要在后续引入正式队列、SQLite/Postgres 或对象存储、集中日志、监控告警、自动重试策略和安全扫描。
