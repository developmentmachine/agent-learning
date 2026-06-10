# Example: API gateway 503 after deploy

### 问题 / 背景

API 返回 503，告警关键字 `upstream connect error`，触发于发布后约 5 分钟，
影响读路径约 30% 请求。

### 过程（定位）

1. 在日志平台按 `status=503` + `service=api-gateway` 过滤最近 15 分钟 → 错误
   集中在 `/v1/items` 路由。
2. 对单条请求查 trace → upstream 为 `catalog-service`，connect timeout 3s。
3. 查 catalog 实例健康检查 → 新副本 Ready 但 readiness 探针失败（DB 连接池耗尽）。
4. 对照发布事件时间线 → 与 HPA 扩容 + 连接池默认上限重合。

### 方案（处理）

1. 临时：将 catalog 副本数固定在发布前水平，避免继续扩容放大连接数。
2. 配置：调高 pool `max_connections` 或降低 per-pod 并发（按 runbook 变更窗口执行）。
3. 验证：5 分钟内 503 率降至基线；抽样 trace 无 connect timeout。
4. 若 30 分钟内无法恢复 → 按 `escalation` skill 联系 DBA 与平台 oncall。

#### 机制说明

Readiness 通过但业务握手仍抢连接池时，网关会把流量打到「健康但饱和」的副本；
扩容会线性放大总连接需求。
