# 贡献指南

感谢参与 `vision-translation`。项目刻意保持小而稳定：

```text
任意 Agent ─▶ 社区或官方 Bridge ─▶ 唯一 Core ─▶ <vision-context>
```

社区扩展能力的主要方式是增加 Bridge，而不是让 Core 知道更多 Agent。

## 职责边界

| 层 | 文件 | 职责 |
|---|---|---|
| Core | `vision_translation.py` | VLM 调用、解析、坐标、几何、上下文渲染 |
| 跨语言协议 | `cli.py`、`PROTOCOL.md` | 输入、JSON 输出、状态、版本 |
| Bridge | `__init__.py`、`adapters/` | Agent 工具注册、附件、生命周期和状态映射 |
| 测试 | `tests/`、各 Bridge smoke test | 离线验证 Core、协议和接入映射 |

## 两级审查门槛

| 变更 | 门槛 |
|---|---|
| **Core** | 高：行为或 API 变更先讨论；它会影响全部 Bridge |
| **协议** | 高：先更新规范，保持兼容或明确提升版本 |
| **Bridge** | 低：薄接入、说明完整、离线 smoke test 通过即可；社区 Bridge 自行维护 |

这样的不对称是设计目标：Core 保持不变，社区可以低成本连接任意 Agent。

## 铁律：Bridge 不复制 Core

Bridge 中不得重新实现：

- 辅助 VLM 提示词或请求；
- 容错 JSON 解析；
- `norm-1000 xyxy` 坐标校验与归一化；
- 空间关系计算；
- `<vision-context>` 渲染或预算裁剪。

Python Bridge 直接导入 `vision_translation.py`；其他语言通过 `cli.py`。
启动开销应通过长驻 MCP 或优化 CLI 解决，不能通过复制逻辑解决。

## 开始开发

```bash
git clone <your-fork>
cd vision-translation
python -m pytest tests/ -v
python adapters/_template/smoke_test.py
```

这些检查离线运行，不需要 API Key。进行真实端到端检查时：

```bash
export OPENROUTER_API_KEY=...
python cli.py path/to/image.jpg "what is the layout?"
```

### pytest 与连字符目录

仓库根既是 Hermes 插件包，目录名 `vision-translation` 又包含连字符。根
`__init__.py` 因此使用“先相对导入、失败后绝对导入”的双模式，`pyproject.toml`
把根目录加入 pytest 的 `pythonpath`。不要把该 `try/except ImportError`
简化为纯相对导入，否则 pytest 收集会出现
`attempted relative import with no known parent package`。

## 增加 Bridge

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

Bridge 可以实现宿主特有的附件解析、工具命名、UI 和生命周期，但不得把这些
要求反向放进 Core。

## 修改协议

1. 先修改 [PROTOCOL.md](PROTOCOL.md)，它是唯一规范。
2. 再修改 `cli.py`，模块文档只保留摘要并链接规范。
3. 保持 stdout 只有一个 JSON 对象，所有日志写 stderr。
4. 同步 `cli.py` 的 `CORE_VERSION` 与 `plugin.yaml` 的 `version`。
5. 破坏兼容的形状变更提升 `protocol` 和仓库主版本。
6. 只在引用协议的地方更新其他文档，避免复制完整规范。

## 修改 Core

1. 先开 Issue 说明行为变化、收益和对全部 Bridge 的影响。
2. 保持导入纯净：导入时无网络、无 argparse、无输出。
3. 不在 Core 中加入任何 Agent、工具协议或 UI 分支。
4. 保持 `<vision-context>` 兼容；有意破坏兼容时按协议流程讨论。
5. 为解析、坐标、几何、预算和失败关闭行为补充离线测试。
6. 同步版本并验证现有 Bridge smoke test。

## PR 检查清单

- [ ] Bridge 未复制 Core 逻辑。
- [ ] `python -m pytest tests/ -v` 通过。
- [ ] 新增或修改的 Bridge 有离线 smoke test。
- [ ] 新 Bridge 已登记到 `ADAPTERS.md`。
- [ ] `CORE_VERSION` 与 `plugin.yaml` 版本一致。
- [ ] 协议变更先更新 `PROTOCOL.md`。
- [ ] CLI stdout 仍为单个 JSON，状态和退出码有文档。
- [ ] 文档命令、相对链接和实现保持一致。
- [ ] 没有提交 API Key、图片隐私数据或其他凭据。

## CI

`.github/workflows/ci.yml` 在 Python 3.10、3.11、3.12 上运行：

- 离线 Core 与协议 pytest；
- 社区模板 smoke test；
- MCP Bridge smoke test；
- `--self-check` 和 `--protocol-version` stdout JSON 纯度检查；
- `cli.CORE_VERSION == plugin.yaml version` 一致性检查。

CI 不注入 `OPENROUTER_API_KEY`。无 Key 的 `--self-check` 返回退出码 0、
`status: unavailable` 和 `reason: no_api_key`，这是协议行为而不是失败。

## 代码与文档风格

- Core 兼容 Python 3.9+，只依赖标准库；Pillow 可选。CI 测试 Python 3.10+。
- 公共函数使用类型提示；Docstring 描述契约。
- Core 不 `print`；CLI 日志写 stderr；协议 stdout 只写 JSON。
- 协议细节只在 `PROTOCOL.md` 定义，其他文档链接过去。
- 文档应区分 Core、Bridge 与 Agent，不能把某个官方 Bridge 写成 Core 前提。

## 许可证

MIT © 2026 Binglun Li。提交贡献即表示同意以相同许可证发布。
