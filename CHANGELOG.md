# 变更记录

所有重要变更记录于此。格式遵循
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，版本遵循
[SemVer](https://semver.org/)。

## [Unreleased]

### 新增

- **MCP Bridge**（`adapters/mcp/`）：以 stdio MCP Server 暴露单一
  `vision_translate` 工具，支持 dsh、Claude Code、Cursor、Hermes 等任意
  MCP Host。Server 直接导入 Core 并复用 `cli._classify`，不复制逻辑；
  `unavailable` 保持为正常的失败关闭结果。包含无 Key、无网络的离线 smoke
  test 和各 Host 配置说明。
- **dsh 官方 preset**（`adapters/mcp/dsh-preset.yml`）：通过
  `@deepseek-ai/dsh-mcp-client` 将 MCP Bridge 接入 dsh Profile，模型工具名为
  `mcp__vision__vision_translate`。是否需要处理附件或富 UI 的原生 Bridge，
  继续在 `ADAPTERS.md` 中说明。
- **dsh 原生插件**（`adapters/dsh/`）：官方 Cordis 插件，注册工具
  `vision_translate`，通过 `ctx.attachments.readImage` 解析 dsh 附件 ref
  （`sha256:<hex>`）→ b64 stdin Envelope → spawn `cli.py`（PROTOCOL v1）。
  零运行时依赖，离线 node:test 测试套件；与 MCP preset 是互补路径
  （原生插件支持 Web UI 附件，preset 仅接收文件路径）。

### 变更

- 重写 README 与全部 Markdown 说明文档，统一为“一个稳定 Core、任意 Agent
  通过 Bridge 接入”的架构叙事；修正调用框图，并保留心路历程、使用方式、
  协议、限制和贡献规则。
- `ADAPTERS.md` 注册 MCP 与 dsh preset，并明确社区 Bridge 的低门槛贡献路径。
- CI 增加 MCP Bridge smoke test。
- `adapters/mcp/requirements.txt` 限制为 `mcp>=1.0,<2.0`，因为 2.0 移除了
  当前 Server 使用的 `mcp.server.fastmcp` API。

## [0.2.0] — 2026-08-15

### 新增

- **CLI 协议 Bridge**（`cli.py`，PROTOCOL v1）：任意 Agent 或语言都可通过
  单个 JSON 请求/响应访问 Core。stdout 仅输出一个 JSON；状态为 `ok`、
  `unavailable`（失败关闭、退出码 0）或 `error`（退出码 1–2）。
- 支持 argv 图片路径和携带路径/Base64 图片的 stdin JSON Envelope。
- 只读握手命令 `--self-check`、`--protocol-version`，不使用 Token 和网络。
- 离线 Core 与协议测试，Mock VLM HTTP 边界，不需要 API Key。
- 社区 Adapter 模板：spawn、JSON 解析、状态映射和 smoke test。
- `ADAPTERS.md`、`CONTRIBUTING.md` 和协议唯一规范 `PROTOCOL.md`。
- GitHub Actions CI：Python 3.10–3.12 pytest、模板 smoke test、stdout 纯度和
  `cli.CORE_VERSION == plugin.yaml version` 检查。
- 最小 `pyproject.toml` pytest 配置，无运行时依赖。

### 变更

- `plugin.yaml` 版本由 `0.1.0` 升至 `0.2.0`。
- 根 `__init__.py` 增加包相对/顶层绝对双模式导入，兼容带连字符的插件目录和
  pytest 收集。
- README 增加 CLI 协议与项目结构。

## [0.1.0] — 2026-08-14

### 新增

- 首次发布 Hermes Agent 插件 **Translation with Visual Primitives**：
  `vision_translation.py` Core 和 `vision_translate` 工具。
- 实现图片 → 辅助 VLM 结构化 JSON → `norm-1000 xyxy` 视觉基元 → 程序计算
  空间关系 → `<vision-context>` 文本的完整流程。
- `demos/vision_translate_demo.py` 端到端 Demo；演示包含额外文本 LLM 步骤，
  生产集成不需要该步骤。
- 同日代码审查：删除死代码、增加越界坐标警告，并整理模块语言。
