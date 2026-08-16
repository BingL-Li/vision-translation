# PROTOCOL v1 Specification

This document is the **single source of truth** for the `vision-translation` CLI protocol. `cli.py` is the implementation; when README, Bridge documentation, or the template conflicts with this document, this document wins.

# PROTOCOL v1 规范

本文是 `vision-translation` CLI 协议的**唯一规范**。`cli.py` 是实现；README、Bridge 文档或模板与本文冲突时，以本文为准。

The protocol is the cross-language boundary between non-Python Bridges and the single Core. The Core produces `<vision-context>`; the CLI only handles input, versioning, status, and JSON envelopes.

该协议是非 Python Bridge 连接唯一 Core 的跨语言边界。Core 输出 `<vision-context>`，CLI 只负责输入、版本、状态和 JSON 封装。

## 1. Output contract

## 1. 输出契约

stdout must contain exactly one JSON object. All human-readable logs go to stderr.

stdout 必须且只能输出一个 JSON 对象。所有人类可读日志写入 stderr。

A Bridge should be able to call `JSON.parse(stdout)` directly; a parse failure is a CLI protocol defect.

Bridge 应能直接执行 `JSON.parse(stdout)`；解析失败属于 CLI 协议缺陷。

Every response includes:

每个响应都包含：

```json
{"protocol": 1, "core_version": "0.2.0", "...": "..."}
```

## 2. Three statuses

## 2. 三种状态

### `ok`

Visual context was generated successfully and the exit code is 0.

视觉上下文已生成，退出码 0：

```json
{
  "protocol": 1,
  "core_version": "0.2.0",
  "status": "ok",
  "context": "<vision-context>…</vision-context>",
  "model": "xiaomi/mimo-v2.5"
}
```

### `unavailable`

The protocol completed normally, but reliable visual context could not be produced; the exit code is 0.

协议正常，但当前无法可靠地产生视觉上下文，退出码 0：

```json
{
  "protocol": 1,
  "core_version": "0.2.0",
  "status": "unavailable",
  "unavailable": {"reason": "no_api_key"}
}
```

This is a **legal fail-closed result**. A Bridge should provide an explicit fallback or tell the user that vision is unavailable; it must not guess the image contents.

这是**合法的失败关闭结果**。Bridge 应触发明确的回退或告知用户当前不可见，不能猜测图片内容。

| `reason` | Meaning |
|---|---|
| `no_api_key` | No OpenRouter key was found in the environment, `~/.hermes/.env`, or `~/.env` |
| `auth` | OpenRouter returned HTTP 401/403 |
| `rate_limited` | OpenRouter returned HTTP 429 |
| `upstream` | Another upstream HTTP or network error |
| `vlm_invalid_output` | The VLM returned unusable JSON three times in a row |
| `invalid_image` | The image is unreadable, empty, or has invalid Base64 |

| `reason` | 含义 |
|---|---|
| `no_api_key` | 环境、`~/.hermes/.env` 和 `~/.env` 均未找到 OpenRouter Key |
| `auth` | OpenRouter 返回 HTTP 401/403 |
| `rate_limited` | OpenRouter 返回 HTTP 429 |
| `upstream` | 其他上游 HTTP 或网络错误 |
| `vlm_invalid_output` | VLM 连续三次返回不可用 JSON |
| `invalid_image` | 图片不可读、为空或 Base64 无效 |

Implementations may add `message`, but Bridge logic may depend only on the stable `reason`.

实现可以附加 `message`，但 Bridge 逻辑只能依赖稳定的 `reason`。

### `error`

The call is invalid or the CLI encountered an internal error; the exit code is non-zero.

调用本身不合法，或 CLI 出现内部错误，退出码非 0：

```json
{
  "protocol": 1,
  "core_version": "0.2.0",
  "status": "error",
  "error": {"code": "usage", "message": "human-readable detail"}
}
```

| `code` | Meaning | Exit code |
|---|---|---|
| `usage` | Invalid argv or stdin envelope | 2 |
| `image_not_found` | The path does not exist | 1 |
| `internal` | Any other internal error | 1 |

| `code` | 含义 | 退出码 |
|---|---|---|
| `usage` | argv 或 stdin Envelope 不合法 | 2 |
| `image_not_found` | 路径不存在 | 1 |
| `internal` | 其他内部错误 | 1 |

An existing file that is unreadable or empty is `unavailable / invalid_image`, not `image_not_found`.

已存在但不可读或为空的文件属于 `unavailable / invalid_image`，不是 `image_not_found`。

## 3. Exit codes

## 3. 退出码

| Exit code | Status |
|---|---|
| 0 | `ok` or `unavailable` |
| 1 | `error`: `image_not_found` / `internal` |
| 2 | `error`: `usage` |

| 退出码 | 状态 |
|---|---|
| 0 | `ok` 或 `unavailable` |
| 1 | `error`：`image_not_found` / `internal` |
| 2 | `error`：`usage` |

A Bridge must read `status` first; exit codes mainly serve shell users.

Bridge 必须先读取 `status`；退出码主要服务 Shell 用户。

## 4. Input

## 4. 输入

### argv input

### argv 输入

```bash
python cli.py <image_path> ["question"]
```

The first argument is the image path; remaining arguments are joined into the question.

第一个参数是图片路径，其余参数会合并为问题。

### stdin Envelope

For separate filesystems, containers, or remote Bridges, stdin is recommended:

跨文件系统、容器或远程 Bridge 推荐使用 stdin：

```json
{
  "protocol": 1,
  "image": {"path": "/abs/or/rel/path"},
  "question": "optional guiding question",
  "options": {"model": "provider/model", "max_objects": 16}
}
```

The `image` object may instead contain Base64; the two forms are mutually exclusive:

或在 `image` 中使用 Base64，两者互斥：

```json
{
  "protocol": 1,
  "image": {"b64": "<base64>", "ext": ".png"},
  "question": "",
  "options": {}
}
```

- argv takes precedence when argv and stdin are both present.
- `max_objects` is finally clamped to 1–16.
- Unknown fields are ignored; missing optional fields use their documented defaults.
- The current implementation accepts only `protocol: 1`.

- argv 与 stdin 同时存在时，argv 优先。
- `max_objects` 最终限制在 1–16。
- 未知字段被忽略，缺失的可选字段使用默认值。
- 当前实现只接受 `protocol: 1`。

## 5. Read-only handshakes

## 5. 只读握手

The following commands do not read images, use tokens, or access the network.

以下命令不读取图片、不使用 Token、不访问网络。

### Self-check

### 自检

```bash
python cli.py --self-check
```

```json
{
  "protocol": 1,
  "core_version": "0.2.0",
  "status": "ok",
  "checks": {
    "openrouter_key": true,
    "key_source": "env",
    "core_import": "ok"
  }
}
```

Without a key, the command still exits 0 with `status: unavailable` and `unavailable.reason: no_api_key`. `key_source` may be `env`, the absolute `.env` path that was read, or `null`.

没有 Key 时仍退出 0，`status` 为 `unavailable`，并包含 `unavailable.reason: no_api_key`。`key_source` 可以是 `env`、读取到的 `.env` 绝对路径或 `null`。

### Version

### 版本

```bash
python cli.py --protocol-version
```

```json
{
  "protocol": 1,
  "core_version": "0.2.0",
  "status": "ok",
  "cli": "0.2.0"
}
```

The exit code is 0.

退出码为 0。

## 6. Version rules

## 6. 版本规则

- `protocol`: Envelope and response shape. Breaking changes must raise the protocol number and the repository major version; Bridges declare their compatible versions.
- `core_version`: Core behavior version without changing the protocol shape. It must match `plugin.yaml` `version`; CI checks this.
- `cli`: CLI implementation version.

- `protocol`：Envelope 和响应形状。破坏兼容性的修改必须提升协议号，并提升仓库主版本；Bridge 声明其兼容版本。
- `core_version`：不改变协议形状的 Core 行为版本。必须与 `plugin.yaml` 中的 `version` 同步，CI 会检查。
- `cli`：CLI 实现版本。

## 7. Bridge compatibility rules

1. Do not assume fields that this document does not guarantee.
2. Ignore unknown response fields.
3. Use `unavailable.reason` for logic; `message` is display-only.
4. Use the documented defaults when optional fields are absent.
5. Do not treat `unavailable` as a protocol crash or fabricate visual content in that state.
6. Do not parse `<vision-context>` to recompute coordinates or relations; it is the Core's final result.

1. 不假设存在本文未保证的字段。
2. 忽略未知响应字段。
3. 使用 `unavailable.reason` 做逻辑判断，`message` 只用于展示。
4. 缺失可选字段时使用本文定义的默认行为。
5. 不把 `unavailable` 当作协议崩溃，也不在该状态下编造视觉内容。
6. 不解析 `<vision-context>` 后重算坐标或关系；它是 Core 的最终结果。
