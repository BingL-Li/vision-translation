# 变更记录

所有重要变更记录于此。格式遵循
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，版本遵循
[SemVer](https://semver.org/)。

## [0.2.2] — 2026-08-18

### 变更

- **Hermes 侧发布回归官方机制**：删除自造的 `adapters/hermes/upgrade.sh`
  （与 Hermes 原生 `hermes plugins update` 重复且功能更弱——官方命令还负责
  安装元数据同步、过期字节码清理、`.example` 文件拷贝和新增能力重授权）。
  Hermes 插件升级现为两条官方命令：`hermes plugins update
  vision-translation` + `hermes gateway restart`。
- README / ADAPTERS / CONTRIBUTING 的发布循环文档同步改为以官方命令为准，
  保留 `adapters/dsh/upgrade.sh`（dsh 无原生 update 命令，脚本是 `dsh
  plugin add` 的薄封装，合理保留）。

## [0.2.1] — 2026-08-18

### 修复

- **Cloudflare-protected 网关适配**（`e171c9e`）：Core 使用 urllib 默认
  User-Agent 调 opencode.ai 等 Cloudflare 保护的 OpenAI 兼容端点时被
  HTTP 403 error 1010 拦截——请求头增加 `User-Agent: curl/8.5.0`
  （实测 UA 字符串是唯一判定变量，TLS 指纹不受影响）。
- **VLM 三件套全链注入**（`e171c9e`）：`cli._ensure_key` 此前只注入
  `VISION_TRANSLATE_API_KEY` 与 `VISION_TRANSLATE_BASE_URL`，漏了
  `VISION_TRANSLATE_VLM`——网关环境缺该变量时静默落回带 OpenRouter 前缀
  的默认模型名（`xiaomi/mimo-v2.5`），在裸模型 ID 端点（如 opencode-go 的
  `mimo-v2.5`）上报 401 ModelError。`analyze()` 同样改为读取该环境变量。

### 新增

- **Hermes 发布交付侧**（`c1bb2b8`）：`adapters/hermes/upgrade.sh` 以 git
  方式（fetch + checkout）刷新 Hermes 插件副本，补充发布循环缺失的第二条
  交付腿（npm/dsh 之外）；配套 CONTRIBUTING 规则、README 与 ADAPTERS 双翼
  发布循环文档。搭配 `adapters/dsh/upgrade.sh` 一起执行即完成一次双侧发布。

### 变更

- 修复 CHANGELOG 中 0.2.0 版本号重复使用的问题：2026-08-15 的原 0.2.0
  条目（CLI 协议 Bridge，从未发布）改标为 `0.2.0-rc.1`；0.2.0 正式版
  仅保留 2026-08-17 的 VLM 配置化 + MCP Bridge + dsh 插件条目。

## [0.2.0] — 2026-08-17

### 新增

- **VLM 通道配置化（OpenAI 兼容端点三件套）**：Core 的 `_call` 现在优先读取
  `VISION_TRANSLATE_BASE_URL` 与 `VISION_TRANSLATE_API_KEY`，并回退到
  `OPENROUTER_API_KEY` / 默认 OpenRouter 地址，任何 OpenAI 兼容的
  `/chat/completions` 端点（OpenAI、DeepSeek、opencode、vLLM、Ollama、
  LiteLLM 等）都可直接使用；CLI 的 `_key_status`、`_ensure_key`、
  `--self-check` 同步支持两个 key 名与 `.env` 中的 base URL。默认值保持
  OpenRouter 向后兼容，老用户零迁移成本。
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

## [0.2.0-rc.1] — 2026-08-15

> 0.2.0 的候选版本（CLI 协议 Bridge），从未发布到 npm；正式 0.2.0 见 2026-08-17 条目。

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
