# Bridge 生态与注册表

本项目采用 **一个 Core、任意 Agent、各自 Bridge** 的结构。仓库目录沿用
`adapters/` 这一实现名称；文档中的 **Bridge** 指连接 Agent 与 Core 的完整
接入层，可以是原生插件、MCP Server，也可以是消费 CLI 协议的 Adapter。

```text
Agent ──图片/问题──▶ Bridge ──调用──▶ vision_translation.py
Agent ◀─上下文/状态── Bridge ◀────── <vision-context>
```

Bridge 只处理宿主特有的工具注册、附件、进程生命周期、协议和状态映射。提示词、
VLM 请求、容错 JSON 解析、坐标归一化、几何关系和上下文渲染始终由唯一 Core
负责。

## 两种接入方式

### 进程内导入

Python Bridge 可以直接导入 `vision_translation.py`，避免启动子进程。
Hermes 原生插件和 MCP Bridge 使用这种方式。它们可以复用 `cli._classify`
完成统一状态分类，但不能复制 Core 逻辑。

### PROTOCOL v1

其他语言、容器或隔离进程通过 `cli.py`：

```text
Bridge ──spawn──▶ python cli.py <image> ["question"]
   │                    │
   │                    └─▶ Core → <vision-context>
   ▼
JSON.parse(stdout) ──▶ status:
   ok           → 使用 context
   unavailable  → 合法的失败关闭结果；回退或告知不可见
   error        → 请求错误或内部错误；向宿主暴露
```

stdin JSON Envelope 还能直接携带 Base64 图片，适合不共享文件系统的环境。
响应结构、退出码和版本规则以 [PROTOCOL.md](PROTOCOL.md) 为唯一规范。

## 注册表

| Bridge | 语言 | 目标 Agent / Host | 状态 | 维护者 |
|---|---|---|---|---|
| [Hermes](__init__.py) | Python | Hermes Agent | 官方、进程内原生插件 | [BingL-Li](https://github.com/BingL-Li) |
| [MCP](adapters/mcp/) | Python | dsh、Claude Code、Cursor、Hermes、Codex 等 MCP Host | 官方、stdio MCP Server，进程内导入 Core | [BingL-Li](https://github.com/BingL-Li) |
| [dsh preset](adapters/mcp/dsh-preset.yml) | YAML | dsh | 官方配置，通过 `@deepseek-ai/dsh-mcp-client` 连接 MCP Bridge | [BingL-Li](https://github.com/BingL-Li) |
| [社区模板](adapters/_template/) | Python 示例 | 任意 Agent / 任意语言 | 脚手架，通过 CLI | — |

社区 Bridge 由其贡献者自行维护，注册表应明确维护者和兼容协议。CI 不会自动发现
所有目录；新 Bridge 必须提供 smoke test，并在工作流中明确接入相应检查。

## 社区贡献 Bridge

1. 先判断宿主是否支持 MCP；支持时优先复用官方 MCP Bridge。
2. MCP 无法满足附件、UI 或生命周期需求时，复制 `adapters/_template/`。
3. 只实现 Agent 与 Core 之间的薄接入。
4. 提供安装、配置、调用和协议兼容说明。
5. 提供不使用密钥和网络的 smoke test。
6. 在上方注册表登记 Bridge、目标宿主、状态和维护者。
7. 按 [CONTRIBUTING.md](CONTRIBUTING.md) 提交 PR。

这是一条有意保持低门槛的贡献路径：社区无需修改稳定 Core，也能让新 Agent
获得同样的视觉翻译能力。

## Bridge 铁律

1. **不得复制 Core。** 不得重写提示词、VLM 调用、JSON 容错、框处理、关系
   推导或 `<vision-context>` 渲染。
2. **协议 stdout 必须纯净。** 消费 CLI 时，`JSON.parse(stdout)` 必须始终
   成功；日志写 stderr。
3. **按 `status` 分支。** `unavailable` 是退出码 0 的合法结果，不是崩溃；
   不得因此猜测或编造图片内容。
4. **无共享文件系统时优先 stdin Envelope。** 使用
   `{"protocol":1,"image":{"b64":"…","ext":".png"}}`。
5. **声明兼容版本。** Bridge README 和本注册表应说明支持的协议版本。
6. **宿主逻辑留在 Bridge。** 附件解析、工具命名、UI 展示、重连和热更新不应
   进入 Core。

## dsh 原生 Bridge 的判断

dsh 已有原生 MCP Client，因此当前官方路径是
[`dsh-preset.yml`](adapters/mcp/dsh-preset.yml)。只有 MCP 无法提供以下宿主
特性时，独立的 `adapters/dsh/` 才值得维护：

- Web UI 上传只以内存对象存在，无法向 MCP 暴露文件路径；
- 需要 `<vision-context>` 的富 UI 展示；
- 需要 Cordis 原生生命周期或 HMR。

在这些需求被验证前，不为“原生”而重复实现 Bridge。

## 版本兼容

- `protocol` 描述请求/响应 Envelope。破坏性变更提升协议号和仓库主版本。
- `core_version` 描述不破坏 Envelope 的 Core 行为版本，并与
  `plugin.yaml` 的 `version` 保持一致。
- 未知响应字段必须可忽略，缺失可选字段使用文档默认值。

## FAQ

**为什么不要求所有 Bridge 都启动 CLI？**

Python Bridge 直接导入 Core 更简单、更快；CLI 是跨语言和跨进程边界，不是
Core 的替代品。两条路径必须落到同一个 `vision_translation.py`。

**每次启动 Python 太慢怎么办？**

优先使用长驻的 MCP Server，或提出 CLI 冷启动优化；不要在 Bridge 中复制 Core。

**为什么不把每个 Agent 的支持都写入 Core？**

这样会让宿主变化污染视觉语义并提高所有用户的维护成本。Agent 数量可以增长，
Core 的职责和输出契约应保持稳定。
