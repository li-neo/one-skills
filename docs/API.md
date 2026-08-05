# HTTP API

启动：

```bash
export ONE_SKILLS_API_TOKEN="replace-with-a-long-random-secret"
one serve --workspace . --host 127.0.0.1 --port 8765
```

非 loopback 地址没有 Token 时会拒绝启动。除 `/health` 外，所有请求都需要：

```http
Authorization: Bearer <ONE_SKILLS_API_TOKEN>
```

## 接口

### `GET /health`

返回进程健康状态，不包含数据库或来源信息。

### `GET /v1/search`

参数：

- `q`：查询文本
- `access`：可重复的访问等级
- `tenant`：租户 ID
- `principal`：主体 ID

检索在全文和向量召回前执行 tenant/principal ACL 和 active-version 过滤。

### `POST /v1/jobs`

请求体上限 1 MiB，且必须为 `application/json`：

```json
{
  "type": "distill",
  "payload": {
    "sources": ["./docs/example.md"],
    "type": "content",
    "name": "example",
    "access": "private-local"
  },
  "max_attempts": 3
}
```

API 只入队，不同步执行蒸馏。由 `one job worker --owner <id>` 领取 lease 并运行。

### `GET /v1/jobs/<job-id>`

查询任务状态、尝试次数、结果或错误。任务状态变化写入 append-only audit events。

## 安全边界

- 不提供任意 SQL、文件读取或命令执行接口。
- 请求体严格限长。
- API 不返回模型密钥、数据库 DSN 或原始私有来源。
- 对公网提供服务时应放在 TLS 反向代理之后，并使用独立身份系统替换静态 Token。
