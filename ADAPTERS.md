# Bridge Ecosystem and Registry

This project uses one Core, any Agent, and a dedicated Bridge for each host. The repository keeps the implementation directory name `adapters/`; in this documentation, **Bridge** means the complete integration layer between an Agent and the Core, whether it is a native plugin, an MCP Server, or an Adapter consuming the CLI protocol.

# Bridge 生态与注册表

本项目采用 **一个 Core、任意 Agent、各自 Bridge** 的结构。仓库目录沿用 `adapters/` 这一实现名称；文档中的 **Bridge** 指连接 Agent 与 Core 的完整接入层，可以是原生插件、MCP Server，也可以是消费 CLI 协议的 Adapter。

```text
Agent ──image/question──▶ Bridge ──call──▶ vision_translation.py
Agent ◀─context/status── Bridge ◀──────── <vision-context>
```

A Bridge handles host-specific tool registration, attachments, process lifetime, protocol, and status mapping. Prompts, VLM requests, tolerant JSON parsing, coordinate normalization, geometric relations, and context rendering always remain in the single Core.

Bridge 只处理宿主特有的工具注册、附件、进程生命周期、协议和状态映射。提示词、VLM 请求、容错 JSON 解析、坐标归一化、几何关系和上下文渲染始终由唯一 Core 负责。

## Two integration paths

## 两种接入方式

### In-process import

### 进程内导入

A Python Bridge can import `vision_translation.py` directly and avoid a child process. The Hermes native plugin and MCP Bridge use this path. They may reuse `cli._classify` for consistent status classification, but may not copy Core logic.

Python Bridge 可以直接导入 `vision_translation.py`，避免启动子进程。Hermes 原生插件和 MCP Bridge 使用这种方式。它们可以复用 `cli._classify` 完成统一状态分类，但不能复制 Core 逻辑。

### PROTOCOL v1 (CLI protocol)

### PROTOCOL v1 协议

Other languages, containers, or isolated processes use `cli.py`:

其他语言、容器或隔离进程通过 `cli.py`：

```text
Bridge ──spawn──▶ python cli.py <image> ["question"]
   │                    │
   │                    └─▶ Core → <vision-context>
   ▼
JSON.parse(stdout) ──▶ status:
   ok           → use context
   unavailable  → legal fail-closed result; fall back or report unavailable
   error        → request or internal error; expose to the host
```

The stdin JSON envelope can also carry a Base64 image directly, which is useful when filesystems are not shared. Response shape, exit codes, and version rules are defined only by [PROTOCOL.md](PROTOCOL.md).

stdin JSON Envelope 还能直接携带 Base64 图片，适合不共享文件系统的环境。响应结构、退出码和版本规则以 [PROTOCOL.md](PROTOCOL.md) 为唯一规范。

## Registry

## 注册表

| Bridge | Language | Target Agent / Host | Status | Maintainer |
|---|---|---|---|---|
| [Hermes](__init__.py) | Python | Hermes Agent | Official, in-process native plugin | [BingL-Li](https://github.com/BingL-Li) |
| [MCP](adapters/mcp/) | Python | dsh, Claude Code, Cursor, Hermes, Codex, and other MCP Hosts | Official stdio MCP Server; imports Core in-process | [BingL-Li](https://github.com/BingL-Li) |
| [dsh native plugin](adapters/dsh/) | JavaScript (Node/Cordis) | dsh | Official Cordis plugin; attachment ref → Base64 stdin envelope → `cli.py` (PROTOCOL v1) | [BingL-Li](https://github.com/BingL-Li) |
| [dsh preset](adapters/mcp/dsh-preset.yml) | YAML | dsh | Official lightweight configuration connecting to the MCP Bridge | [BingL-Li](https://github.com/BingL-Li) |
| [Community template](adapters/_template/) | Python example | Any Agent / language | CLI-based scaffold | — |

| Bridge | 语言 | 目标 Agent / Host | 状态 | 维护者 |
|---|---|---|---|---|
| [Hermes](__init__.py) | Python | Hermes Agent | 官方、进程内原生插件 | [BingL-Li](https://github.com/BingL-Li) |
| [MCP](adapters/mcp/) | Python | dsh、Claude Code、Cursor、Hermes、Codex 等 MCP Host | 官方、stdio MCP Server，进程内导入 Core | [BingL-Li](https://github.com/BingL-Li) |
| [dsh 原生插件](adapters/dsh/) | JavaScript (Node/Cordis) | dsh | 官方 Cordis 插件：附件 ref → Base64 stdin Envelope → `cli.py`（PROTOCOL v1） | [BingL-Li](https://github.com/BingL-Li) |
| [dsh preset](adapters/mcp/dsh-preset.yml) | YAML | dsh | 官方轻量配置，连接 MCP Bridge | [BingL-Li](https://github.com/BingL-Li) |
| [社区模板](adapters/_template/) | Python 示例 | 任意 Agent / 语言 | CLI 脚手架 | — |

Community Bridges are maintained by their contributors. The registry should state the maintainer and compatible protocol version. CI does not discover every directory automatically; a new Bridge must provide a smoke test and an explicit workflow check.

社区 Bridge 由其贡献者自行维护，注册表应明确维护者和兼容协议。CI 不会自动发现所有目录；新 Bridge 必须提供 smoke test，并在工作流中明确接入相应检查。

## Community Bridge contributions

## 社区贡献 Bridge

1. Check whether the host supports MCP; when it does, prefer the official MCP Bridge.
2. If MCP cannot meet attachment, UI, or lifecycle needs, copy `adapters/_template/`.
3. Implement only the thin integration between the Agent and Core.
4. Document installation, configuration, invocation, and protocol compatibility.
5. Provide a smoke test that uses neither keys nor the network.
6. Register the Bridge, target host, status, and maintainer above.
7. Submit a PR according to [CONTRIBUTING.md](CONTRIBUTING.md).

1. 先判断宿主是否支持 MCP；支持时优先复用官方 MCP Bridge。
2. MCP 无法满足附件、UI 或生命周期需求时，复制 `adapters/_template/`。
3. 只实现 Agent 与 Core 之间的薄接入。
4. 提供安装、配置、调用和协议兼容说明。
5. 提供不使用密钥和网络的 smoke test。
6. 在上方注册表登记 Bridge、目标宿主、状态和维护者。
7. 按 [CONTRIBUTING.md](CONTRIBUTING.md) 提交 PR。

This is intentionally a low-barrier contribution path: the community can give a new Agent the same visual translation capability without modifying the stable Core.

这是一条有意保持低门槛的贡献路径：社区无需修改稳定 Core，也能让新 Agent 获得同样的视觉翻译能力。

## Bridge rules

## Bridge 铁律

1. **Do not copy the Core.** Do not rewrite prompts, VLM calls, tolerant JSON parsing, box handling, relation derivation, or `<vision-context>` rendering.
2. **Keep protocol stdout pure.** When consuming the CLI, `JSON.parse(stdout)` must always succeed; write logs to stderr.
3. **Branch on `status`.** `unavailable` is a valid exit-code-0 result, not a crash; never guess or fabricate image content.
4. **Prefer stdin envelopes without a shared filesystem.** Use `{"protocol":1,"image":{"b64":"…","ext":".png"}}`.
5. **Declare compatibility.** Each Bridge README and this registry should state supported protocol versions.
6. **Keep host logic in the Bridge.** Attachment parsing, tool names, UI, reconnects, and hot reload must not enter the Core.

1. **不得复制 Core。** 不得重写提示词、VLM 调用、JSON 容错、框处理、关系推导或 `<vision-context>` 渲染。
2. **协议 stdout 必须纯净。** 消费 CLI 时，`JSON.parse(stdout)` 必须始终成功；日志写 stderr。
3. **按 `status` 分支。** `unavailable` 是退出码 0 的合法结果，不是崩溃；不得因此猜测或编造图片内容。
4. **无共享文件系统时优先 stdin Envelope。** 使用 `{"protocol":1,"image":{"b64":"…","ext":".png"}}`。
5. **声明兼容版本。** Bridge README 和本注册表应说明支持的协议版本。
6. **宿主逻辑留在 Bridge。** 附件解析、工具命名、UI 展示、重连和热更新不应进入 Core。

## Choosing the native dsh Bridge

## dsh 原生 Bridge 的判断

**Resolved.** The native Cordis plugin is implemented in [`adapters/dsh/`](adapters/dsh/). It registers the dsh `vision_translate` tool, turns dsh image attachments (`sha256:<hex>`) into a stdin Base64 envelope, and spawns `cli.py` (PROTOCOL v1) as the only process. When an image arrives as a Web UI attachment rather than a filesystem path, the native plugin is the official path.

**已解决。** 原生 Cordis 插件已实现在 [`adapters/dsh/`](adapters/dsh/)：注册 dsh 工具 `vision_translate`，通过 `ctx.attachments.readImage` 把 dsh 图片附件（`sha256:<hex>` ref）解析为 stdin Base64 Envelope，并以 spawn `cli.py`（PROTOCOL v1）作为唯一进程。当图片以 Web UI 附件而非文件系统路径到达时，原生插件是官方路径。

The MCP preset (`adapters/mcp/dsh-preset.yml`) remains the **lightweight path**: one stdio server per host, suitable when the host passes a local file path and does not need an npm plugin.

MCP preset（`adapters/mcp/dsh-preset.yml`）仍是**轻量路径**：每宿主一个 stdio server，适合宿主把图片作为本地文件路径传入、且不想安装 npm 插件的场景。

- Native plugin: attachment refs work for Web uploads, no resident server, zero runtime dependencies, and profile HMR.
- MCP preset: simplest one-time setup, but stdio carries strings only, so attachment refs are unavailable.

- 原生插件：支持 Web 上传的附件 ref，无常驻 server 进程，零运行时依赖，并随 profile HMR 热更新。
- MCP preset：单次安装最简单，但 stdio 只传字符串，因此无法接收附件 ref。

Choose per host: use the native plugin when dsh attachment support is required; otherwise the MCP preset is sufficient. Maintain a separate `adapters/dsh/` Bridge only when the host needs:

按宿主按需选择：需要 dsh 附件支持时用原生插件，否则 MCP preset 足够。只有在宿主需要以下特性时，才值得维护独立的 `adapters/dsh/` Bridge：

- Web uploads exist only as in-memory objects and cannot be exposed as file paths.
- Rich UI presentation of `<vision-context>`.
- Native Cordis lifecycle or HMR.

- Web UI 上传只以内存对象存在，无法向 MCP 暴露文件路径。
- 需要 `<vision-context>` 的富 UI 展示。
- 需要 Cordis 原生生命周期或 HMR。

## Version compatibility

## 版本兼容

- `protocol` describes the request/response envelope. Breaking changes raise the protocol number and repository major version.
- `core_version` describes compatible Core behavior and matches `plugin.yaml` `version`.
- Unknown response fields must be ignored; missing optional fields use documented defaults.

- `protocol` 描述请求/响应 Envelope。破坏性变更提升协议号和仓库主版本。
- `core_version` 描述不破坏 Envelope 的 Core 行为版本，并与 `plugin.yaml` 的 `version` 保持一致。
- 未知响应字段必须可忽略，缺失可选字段使用文档默认值。

## FAQ

**Why does every Bridge not have to start the CLI?** A Python Bridge can import the Core directly, while the CLI is the cross-language and cross-process boundary, not a replacement for the Core. Both paths must end at the same `vision_translation.py`.

**为什么不要求所有 Bridge 都启动 CLI？** Python Bridge 直接导入 Core 更简单、更快；CLI 是跨语言和跨进程边界，不是 Core 的替代品。两条路径必须落到同一个 `vision_translation.py`。

**What if starting Python each time is slow?** Prefer a long-lived MCP Server or propose a CLI cold-start optimization; do not copy Core logic into a Bridge.

**每次启动 Python 太慢怎么办？** 优先使用长驻的 MCP Server，或提出 CLI 冷启动优化；不要在 Bridge 中复制 Core。

**Why not put every Agent integration into the Core?** That would let host changes pollute visual semantics and raise maintenance costs for everyone. The Agent count can grow while the Core's responsibilities and output contract remain stable.

**为什么不把每个 Agent 的支持都写入 Core？** 这样会让宿主变化污染视觉语义并提高所有用户的维护成本。Agent 数量可以增长，Core 的职责和输出契约应保持稳定。
