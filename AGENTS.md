# AGENTS.md

Instructions for AI coding assistants (Hermes / dsh / codex / claude-code / opencode) and human contributors working in this repository.

本文件是仓库级规则，作用于所有在此工作的 agent 与人类贡献者。

## Project / 项目

`vision-translation` — Translation with Visual Primitives: one stable visual-translation Core, any Agent plugs in through a Bridge.

- **Core**: `vision_translation.py`（VLM 调用、解析、坐标归一化、几何、上下文渲染）
- **Protocol**: `cli.py` + `PROTOCOL.md`（跨语言输入 / JSON 输出 / 协议版本）
- **Bridges**: `adapters/`（dsh / mcp / hermes；`_template/` 是新 Bridge 的起点）
- **Tests**: `tests/` + 各 Bridge `smoke_test.py`
- **Docs**: `README.md`（总览）、`ADAPTERS.md`（Bridge 生态注册表）、`CONTRIBUTING.md`（贡献指南与两级审查门槛）、`docs/architecture.md`

## Hard rules / 铁律

1. **分支 + PR**：所有改动走分支 + PR，禁止直推 `main` 或 `release/*`。`main` 有分支保护，合并需 review；agent 不自行合并，由维护者在网页合并。
2. **Bridge 不得复制 Core**：不得在 `adapters/` 重新实现 VLM 调用、解析、坐标归一化、几何或上下文渲染 —— 一律调用 Core / 消费 CLI 协议（详见 CONTRIBUTING.md）。
3. **协议变更先改规范**：改动 `cli.py` 前先更新 `PROTOCOL.md`，保持兼容或显式提升协议版本。
4. **发布双翼，不养第三方脚本**：dsh 侧走 `adapters/dsh/upgrade.sh`（npm 发布）；Hermes 侧走官方 `hermes plugins update`（git 拉取）。不再新增/维护其他自造升级脚本。
5. **副本只用 git 更新**：任何安装副本（插件目录、npm 包、MCP server）一律通过 `git pull` / `hermes plugins update` / `npm update` 更新，禁止手工文件拷贝覆盖。

## Review thresholds / 变更门槛

| 变更 | 门槛 |
|---|---|
| Core | 高：行为或 API 变更先讨论；影响所有 Bridge |
| Protocol | 高：先改规范，保持兼容或升版本 |
| Bridge | 低：薄接入 + 文档完整 + 离线 smoke test 通过 |
| Docs | 低：准确、双语 |

## Testing / 测试

```bash
python -m pytest                                   # 全部测试（pyproject 已配 pythonpath=[.]）
python -m pytest tests/                            # Core + 协议
python -m pytest adapters/<bridge>/smoke_test.py   # 单个 Bridge smoke
```

全部离线可跑，无需真 VLM 或真机。改 Core / 协议必须附带通过的单测。

## Language / 语言

文档双语（中文 + English）。新文档、新 README 段落保持双语对齐。

## Git identity / 署名约定

- Hermes 提交署名：`Hermes <hermes@nousresearch.com>`
- 人类提交署名：`Binglun Li`
- 便于 `git log --author` 审计。

## Delegation / 委托约定

代码开发默认交给专业编码 agent（dsh / codex / claude-code / opencode）执行；Hermes 负责调研、评审、测试验证、文档与发布运维，不在本仓库直接写/改业务代码。

## Not in this repo / 不入库的内容

个人内部文档（架构决策复盘、评估报告、部署备忘）不进本公共仓库，保存在个人 vault。仓库内只保留正式文档。