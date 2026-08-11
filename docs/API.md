# HTTP API

启动：

```bash
export ONE_SKILLS_API_TOKEN="replace-with-a-long-random-secret"
one serve --workspace . --host 127.0.0.1 --port 8765 \
  --tenant local --principal local-user --access public
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

tenant、principal 和允许的访问等级只由 `one serve` 的启动参数配置，请求参数不能覆盖身份。检索在全文和向量召回前执行 ACL 和 active-version 过滤。

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
每类 Job 使用固定 payload 字段；所有本地 source、Pack、suite 和 output 路径都必须位于 workspace 内，Worker 执行前会再次校验。远程来源只接受 HTTP(S) URL。

### `GET /v1/jobs/<job-id>`

查询任务状态、尝试次数、结果或错误。任务状态变化写入 append-only audit events。

## 安全边界

- 不提供任意 SQL、文件读取或命令执行接口。
- 请求体严格限长。
- Bearer Token 只证明请求持有服务凭据，不接受请求自行声明 tenant 或 principal。
- API 不返回模型密钥、数据库 DSN 或原始私有来源。
- HTTP API 当前属于 Experimental。对公网提供服务时应放在 TLS 反向代理之后，并使用独立身份系统替换单一静态 Token。
