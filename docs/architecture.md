# 架构

一个 Core，任意 Agent，各自的 Bridge。

```mermaid
flowchart LR
  A["任意 Agent<br/>Hermes · dsh · Claude Code"]
  B["Bridge<br/>每 Agent 一个 · 只做接入与协议映射"]
  C["cli.py<br/>跨语言协议入口 · PROTOCOL v1"]
  D["唯一 Core<br/>vision_translation.py"]
  V["auxiliary VLM<br/>可选 · 只看图返回 JSON"]

  A -- "image + question" --> B
  B -- "进程内 import（Hermes / MCP）" --> D
  B -- "spawn（跨语言/隔离进程）" --> C
  C --> D
  D -. "按需调用" .-> V
  D -- "vision-context" --> B
  B -- "vision-context" --> A
```

## 每部分只做一件事

| 部分 | 职责 |
|---|---|
| Agent | 发图 + 问题，收 vision-context 文本 |
| Bridge | 接入、协议与状态映射，零业务逻辑 |
| cli.py | Core 的跨语言协议入口（PROTOCOL v1，stdin b64） |
| Core | 全部视觉翻译逻辑：VLM JSON → 基元 → 几何 → 文本 |
| VLM | 看图，返回结构化 JSON |

Core 内部流水线：`image → VLM JSON → 规范化基元 norm-1000 xyxy → 几何关系 → <vision-context>`

> 铁律：核心逻辑只在 Core；新增 Agent = 新增一个 Bridge，永不改 Core。
