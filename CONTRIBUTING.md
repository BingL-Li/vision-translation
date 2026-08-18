# Contributing Guide

Thank you for contributing to `vision-translation`. The project is intentionally small and stable:

# 贡献指南

感谢参与 `vision-translation`。项目刻意保持小而稳定：

```text
Any Agent ─▶ community or official Bridge ─▶ single Core ─▶ <vision-context>
```

The main way to extend the project is to add a Bridge, not to make the Core know about more Agents.

社区扩展能力的主要方式是增加 Bridge，而不是让 Core 知道更多 Agent。

## Responsibility boundaries

## 职责边界

| Layer | Files | Responsibility |
|---|---|---|
| Core | `vision_translation.py` | VLM calls, parsing, coordinates, geometry, context rendering |
| Cross-language protocol | `cli.py`, `PROTOCOL.md` | Input, JSON output, status, versioning |
| Bridge | `__init__.py`, `adapters/` | Agent tools, attachments, lifecycle, and status mapping |
| Tests | `tests/`, Bridge smoke tests | Offline validation of Core, protocol, and integration mapping |

| 层 | 文件 | 职责 |
|---|---|---|
| Core | `vision_translation.py` | VLM 调用、解析、坐标、几何、上下文渲染 |
| 跨语言协议 | `cli.py`、`PROTOCOL.md` | 输入、JSON 输出、状态、版本 |
| Bridge | `__init__.py`、`adapters/` | Agent 工具注册、附件、生命周期和状态映射 |
| 测试 | `tests/`、各 Bridge smoke test | 离线验证 Core、协议和接入映射 |

## Two review thresholds

## 两级审查门槛

| Change | Threshold |
|---|---|
| **Core** | High: discuss behavior or API changes first; every Bridge depends on them |
| **Protocol** | High: update the specification first and preserve compatibility or raise the version |
| **Bridge** | Low: a thin integration, complete documentation, and a passing offline smoke test are sufficient; community Bridges are self-maintained |

| 变更 | 门槛 |
|---|---|
| **Core** | 高：行为或 API 变更先讨论；它会影响全部 Bridge |
| **协议** | 高：先更新规范，保持兼容或明确提升版本 |
| **Bridge** | 低：薄接入、说明完整、离线 smoke test 通过即可；社区 Bridge 自行维护 |

This asymmetry is intentional: the Core remains stable while the community can connect any Agent at low cost.

这样的不对称是设计目标：Core 保持不变，社区可以低成本连接任意 Agent。

## Rule: Bridges do not copy the Core

## 铁律：Bridge 不复制 Core

A Bridge must not reimplement:

Bridge 中不得重新实现：

- Auxiliary VLM prompts or requests;
- Tolerant JSON parsing;
- `norm-1000 xyxy` validation and normalization;
- Spatial relation calculation;
- `<vision-context>` rendering or budget trimming.

- 辅助 VLM 提示词或请求；
- 容错 JSON 解析；
- `norm-1000 xyxy` 坐标校验与归一化；
- 空间关系计算；
- `<vision-context>` 渲染或预算裁剪。

Python Bridges import `vision_translation.py` directly; other languages use `cli.py`. Solve startup cost with a long-lived MCP Server or CLI optimization, never by copying logic.

Python Bridge 直接导入 `vision_translation.py`；其他语言通过 `cli.py`。启动开销应通过长驻 MCP 或优化 CLI 解决，不能通过复制逻辑解决。

## Start developing

## 开始开发

```bash
git clone <your-fork>
cd vision-translation
python -m pytest tests/ -v
python adapters/_template/smoke_test.py
```

These checks run offline and do not need an API key. For a real end-to-end check:

这些检查离线运行，不需要 API Key。进行真实端到端检查时：

```bash
export OPENROUTER_API_KEY=...
python cli.py path/to/image.jpg "what is the layout?"
```

### pytest and the hyphenated directory

### pytest 与连字符目录

The repository root is both a Hermes plugin package and a directory named `vision-translation`, which contains a hyphen. Root `__init__.py` therefore uses relative import first and absolute import as a fallback; `pyproject.toml` adds the root to pytest's `pythonpath`. Do not simplify that `try/except ImportError` to a relative-only import, or pytest collection will fail with `attempted relative import with no known parent package`.

仓库根既是 Hermes 插件包，目录名 `vision-translation` 又包含连字符。根 `__init__.py` 因此使用“先相对导入、失败后绝对导入”的双模式，`pyproject.toml` 把根目录加入 pytest 的 `pythonpath`。不要把该 `try/except ImportError` 简化为纯相对导入，否则 pytest 收集会出现 `attempted relative import with no known parent package`。

## Rule: Host plugin copies are updated by git, never by file copy

## 规则：宿主插件副本只用 git 更新，绝不文件拷贝

A host that installs this repository directly as a plugin (e.g. Hermes:
`~/.hermes/plugins/vision-translation`) keeps a **git clone** of the repo and
must refresh it through git only:

```bash
git fetch origin
git checkout -B main origin/main
```

Never sync by copying files from another working tree (`cp -r`, rsync, etc.).
A file copy silently drops local divergence, breaks the link to the upstream
history, and turns the next `git pull` into a conflict — the copy then drifts
from the release, and bugs fixed upstream silently come back on that host.
This convention is enforced by the release loop: `adapters/dsh/upgrade.sh`
covers the npm/dsh delivery leg, and the git/Hermes delivery leg uses the
native Hermes command `hermes plugins update vision-translation` (which pulls
the same git history). Both must run for a release to reach every host.

宿主直接以插件形式安装本仓库时（例如 Hermes 的
`~/.hermes/plugins/vision-translation`），保留的是仓库的 **git clone**，只能
通过 git 更新：

```bash
git fetch origin
git checkout -B main origin/main
```

绝不要从别的工作区用文件拷贝（`cp -r`、rsync 等）同步。文件拷贝会静默丢弃
本地差异、切断与上游历史的联系，并让下一次 `git pull` 变成冲突——副本从此
与发布版本脱节，已在上游修复的 bug 会在该宿主静默复发。发布循环强制执行此
约定：`adapters/dsh/upgrade.sh` 负责 npm/dsh 交付侧，git/Hermes 交付侧使用
Hermes 原生命令 `hermes plugins update vision-translation`（拉取同一份 git
历史）。两侧都执行一次，发布才算送达所有宿主。

## Add a Bridge

## 增加 Bridge

1. Confirm that the official MCP Bridge does not already meet the host's needs.
2. Copy `adapters/_template/` to `adapters/<bridge-name>/`.
3. Implement the thinnest host integration:
   - Python may import the Core directly;
   - other languages start `cli.py` and parse one JSON object;
   - map `ok / unavailable / error` to host results.
4. Write a README covering purpose, installation, configuration, invocation, and protocol version.
5. Write an offline smoke test covering all three statuses without network access or keys.
6. Update the [ADAPTERS.md](ADAPTERS.md) registry.
7. Run the smoke test explicitly in CI; CI does not discover new Bridges automatically.

1. 确认官方 MCP Bridge 是否已经满足宿主需求。
2. 复制 `adapters/_template/` 到 `adapters/<bridge-name>/`。
3. 实现最薄的宿主接入：
   - Python 可直接导入 Core；
   - 其他语言启动 `cli.py` 并解析单个 JSON；
   - 按 `ok / unavailable / error` 映射宿主结果。
4. 编写 README，说明用途、安装、配置、调用方式和协议版本。
5. 编写离线 smoke test，覆盖三种状态且不使用网络和 Key。
6. 更新 [ADAPTERS.md](ADAPTERS.md) 注册表。
7. CI 不会自动发现新 Bridge；在工作流中明确运行其 smoke test。

A Bridge may implement host-specific attachment parsing, tool names, UI, and lifecycle, but those requirements must not be moved into or copied into the Core.

Bridge 可以实现宿主特有的附件解析、工具命名、UI 和生命周期，但不得把这些要求反向放进或复制进 Core。

## Change the protocol

## 修改协议

1. Edit [PROTOCOL.md](PROTOCOL.md) first; it is the single specification.
2. Edit `cli.py` second; keep its module documentation as a summary with a link to the specification.
3. Keep stdout to one JSON object and write all logs to stderr.
4. Keep `cli.py` `CORE_VERSION` synchronized with `plugin.yaml` `version`.
5. Raise `protocol` and the repository major version for incompatible shape changes.
6. Update other documentation only where it references the protocol; do not duplicate the full specification.

1. 先修改 [PROTOCOL.md](PROTOCOL.md)，它是唯一规范。
2. 再修改 `cli.py`，模块文档只保留摘要并链接规范。
3. 保持 stdout 只有一个 JSON 对象，所有日志写 stderr。
4. 同步 `cli.py` 的 `CORE_VERSION` 与 `plugin.yaml` 的 `version`。
5. 破坏兼容的形状变更提升 `protocol` 和仓库主版本。
6. 只在引用协议的地方更新其他文档，避免复制完整规范。

## Change the Core

## 修改 Core

1. Open an Issue describing the behavior change, benefit, and impact on every Bridge.
2. Keep imports pure: no network, argparse, or output at import time.
3. Do not add Agent integrations, tool protocols, or UI branches to the Core.
4. Preserve `<vision-context>` compatibility; discuss intentional breaking changes through the protocol process.
5. Add offline tests for parsing, coordinates, geometry, budget, and fail-closed behavior.
6. Synchronize the version and verify every existing Bridge smoke test.

1. 先开 Issue 说明行为变化、收益和对全部 Bridge 的影响。
2. 保持导入纯净：导入时无网络、无 argparse、无输出。
3. 不在 Core 中加入任何 Agent、工具协议或 UI 分支。
4. 保持 `<vision-context>` 兼容；有意破坏兼容时按协议流程讨论。
5. 为解析、坐标、几何、预算和失败关闭行为补充离线测试。
6. 同步版本并验证现有 Bridge smoke test。

## PR checklist

## PR 检查清单

- [ ] The Bridge does not copy Core logic.
- [ ] `python -m pytest tests/ -v` passes.
- [ ] Every added or changed Bridge has an offline smoke test.
- [ ] Every new Bridge is registered in `ADAPTERS.md`.
- [ ] `CORE_VERSION` matches the `plugin.yaml` version.
- [ ] `PROTOCOL.md` is updated before protocol changes.
- [ ] CLI stdout remains one JSON object and status/exit codes are documented.
- [ ] Documentation commands, relative links, and implementation agree.
- [ ] No API keys, private image data, or other credentials are committed.

- [ ] Bridge 未复制 Core 逻辑。
- [ ] `python -m pytest tests/ -v` 通过。
- [ ] 新增或修改的 Bridge 有离线 smoke test。
- [ ] 新 Bridge 已登记到 `ADAPTERS.md`。
- [ ] `CORE_VERSION` 与 `plugin.yaml` 版本一致。
- [ ] 协议变更先更新 `PROTOCOL.md`。
- [ ] CLI stdout 仍为单个 JSON，状态和退出码有文档。
- [ ] 文档命令、相对链接和实现保持一致。
- [ ] 没有提交 API Key、图片隐私数据或其他凭据。

## CI (Continuous Integration)

`.github/workflows/ci.yml` runs on Python 3.10, 3.11, and 3.12 and checks:

- Offline Core and protocol pytest tests;
- Community template smoke test;
- MCP Bridge smoke test;
- JSON purity for `--self-check` and `--protocol-version`;
- `cli.CORE_VERSION == plugin.yaml version`.

## CI（持续集成）

`.github/workflows/ci.yml` 在 Python 3.10、3.11、3.12 上运行并检查：

- 离线 Core 与协议 pytest；
- 社区模板 smoke test；
- MCP Bridge smoke test；
- `--self-check` 和 `--protocol-version` stdout JSON 纯度；
- `cli.CORE_VERSION == plugin.yaml version` 一致性。

CI does not inject `OPENROUTER_API_KEY`. Without a key, `--self-check` exits 0 with `status: unavailable` and `reason: no_api_key`; this is protocol behavior, not a failure.

CI 不注入 `OPENROUTER_API_KEY`。无 Key 时 `--self-check` 返回退出码 0、`status: unavailable` 和 `reason: no_api_key`，这是协议行为而不是失败。

## Code and documentation style

## 代码与文档风格

- The Core supports Python 3.9+ and uses only the standard library at runtime; Pillow is optional. CI tests Python 3.10+.
- Public functions use type hints; docstrings describe contracts.
- The Core does not `print`; CLI logs use stderr; protocol stdout contains only JSON.
- Protocol details are defined only in `PROTOCOL.md`; other documents link there.
- Documentation distinguishes Core, Bridge, and Agent and does not present an official Bridge as a Core prerequisite.

- Core 兼容 Python 3.9+，只依赖标准库；Pillow 可选。CI 测试 Python 3.10+。
- 公共函数使用类型提示；Docstring 描述契约。
- Core 不 `print`；CLI 日志写 stderr；协议 stdout 只写 JSON。
- 协议细节只在 `PROTOCOL.md` 定义，其他文档链接过去。
- 文档应区分 Core、Bridge 与 Agent，不能把某个官方 Bridge 写成 Core 前提。

## License

## 许可证

MIT © 2026 Binglun Li. Contributions are released under the same license.

MIT © 2026 Binglun Li。提交贡献即表示同意以相同许可证发布。
