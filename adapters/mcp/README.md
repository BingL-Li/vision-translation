# MCP Bridge

MCP Bridge 通过 stdio 暴露一个 `vision_translate` 工具，可连接 dsh、
Claude Code、Cursor、Hermes、Codex 等任意 MCP Host。

它是“一个 Core、任意 Agent”架构中的通用 Bridge：

```text
MCP Host ──JSON-RPC──▶ MCP Bridge ──import──▶ vision_translation.py
         ◀──────────── <vision-context> ◀──── 唯一 Core
```

Server 直接导入 Core，并复用 `cli._classify` 的状态分类；它不启动 CLI，也不
复制提示词、解析、坐标或几何逻辑。设计规则见
[CONTRIBUTING.md](../../CONTRIBUTING.md)。

## 状态映射

| Core / CLI 语义 | MCP 结果 |
|---|---|
| `ok` | 正常返回 `<vision-context>` |
| `unavailable` | 正常工具结果，明确返回 `vision unavailable (reason: …)` 和“不要猜测”提示 |
| `error` | 抛出 MCP 错误，由 Host 展示或按错误类型处理 |

`unavailable` 是失败关闭，不是协议异常；Agent 收到后不得编造图片内容。

## 安装

Core 仍只依赖 Python 标准库；本 Bridge 额外依赖 MCP Python SDK：

```bash
cd adapters/mcp
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

依赖限制为 `mcp>=1.0,<2.0`，因为当前 Server 使用
`mcp.server.fastmcp.FastMCP`，MCP 2.0 已移除该高层 API。

离线验证不需要 Key 或网络：

```bash
.venv/bin/python smoke_test.py
```

手动启动：

```bash
.venv/bin/python server.py
```

stdio 属于 JSON-RPC；不要把 Server 当作交互式终端。stdout 必须保持纯净，
日志只能写 stderr。

## 工具

工具名：`vision_translate`

| 参数 | 类型 | 说明 |
|---|---|---|
| `image` | string | MCP Server 可访问的本地图片路径，必填 |
| `question` | string | 引导解析重点的可选问题 |
| `model` | string | 可选辅助 VLM；为空时读取环境变量或 Core 默认值 |
| `max_objects` | int | 可选基元上限，最终限制为 1–16 |

返回 Core 生成的 `<vision-context>`。如果结果显示视觉不可用，Host Agent 应
告知用户，而不是基于文件名或上下文猜图。

## Host 配置

以下路径必须改成你的仓库绝对路径。建议在 Host 环境或受保护的环境文件中提供
`OPENROUTER_API_KEY`，不要把真实 Key 提交到仓库。

### dsh

dsh 内置 `@deepseek-ai/dsh-mcp-client`。将
[`dsh-preset.yml`](dsh-preset.yml) 的 `- insert:` 块合并到 Profile 的
`cordis.patch.yml`，例如：

```text
~/.dsh/profiles/web/cordis.patch.yml
```

调整 Python 与 `server.py` 路径后，模型看到的工具名为
`mcp__vision__vision_translate`。

### Claude Code

在项目根创建或合并 `.mcp.json`：

```json
{
  "mcpServers": {
    "vision": {
      "command": "/abs/path/to/vision-translation/adapters/mcp/.venv/bin/python",
      "args": [
        "/abs/path/to/vision-translation/adapters/mcp/server.py"
      ],
      "env": {
        "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}"
      }
    }
  }
}
```

如 Host 不展开 `${OPENROUTER_API_KEY}`，请通过其安全配置机制传入环境变量，
不要在共享配置中写明文 Key。

### Cursor

在 `~/.cursor/mcp.json` 使用与 Claude Code 相同的 `mcpServers` 结构。

### Hermes

Hermes 已有进程内原生 Bridge，通常应优先使用。若选择 MCP，则在
`~/.hermes/config.yaml` 配置：

```yaml
mcp_servers:
  vision:
    command: /abs/path/to/vision-translation/adapters/mcp/.venv/bin/python
    args:
      - /abs/path/to/vision-translation/adapters/mcp/server.py
    env:
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
```

Hermes 中工具名为 `mcp_vision_vision_translate`。原生插件和 MCP Bridge 二选一，
避免重复工具和 Schema Token 浪费。

## 限制与扩展

- stdio Server 是长驻进程，每个 Host Session 通常只承担一次 Python 冷启动。
- 当前只接受 MCP Server 本地可访问的文件路径。
- 如果 Host 只传内存 Blob、远程附件或无共享文件系统，应先由 Host Bridge
  落盘并传路径；确实无法处理时再贡献原生 Bridge。
- 宿主附件、UI 和生命周期逻辑属于新 Bridge，不能进入或复制 Core。

Bridge 注册和 dsh 原生接入的判断条件见
[ADAPTERS.md](../../ADAPTERS.md)。
