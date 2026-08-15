# 社区 Bridge 模板

这个目录是连接新 Agent 的最小脚手架。目标不是实现另一套视觉能力，而是把
宿主输入交给唯一 Core，再把结果交回宿主。

```text
你的 Agent ─▶ 你的 Bridge ─▶ cli.py ─▶ vision_translation.py
           ◀─────────────── <vision-context> / 状态
```

Python Bridge 也可以像官方 Hermes 或 MCP Bridge 一样直接导入 Core；模板使用
CLI，是为了展示任意语言都能采用的通用模式。

## 唯一铁律

> **Bridge 不复制 Core。**

不得在 Bridge 中重新实现 VLM 提示、请求、JSON 解析、坐标归一化、空间关系或
`<vision-context>` 渲染。跨语言唯一契约是 `cli.py`，规范见
[PROTOCOL.md](../../PROTOCOL.md)。

## 创建新 Bridge

1. 复制模板：

   ```bash
   cp -r adapters/_template adapters/<your-bridge>
   ```

2. 实现宿主接入：
   - 启动 `python cli.py <image_path> ["question"]`；或
   - 无共享文件系统时向 stdin 写入 Base64 Envelope；
   - 把 stdout 解析为一个 JSON 对象；
   - 根据 `status` 映射宿主工具结果。
3. 编写自己的 README，包含目标 Agent、安装、配置、用法、限制和
   `PROTOCOL v1` 兼容声明。
4. 编写离线 smoke test，覆盖 `ok / unavailable / error`，不得使用真实 Key、
   网络或付费请求。
5. 在 [ADAPTERS.md](../../ADAPTERS.md) 注册 Bridge 和维护者。
6. 在 CI 工作流中显式运行 smoke test，然后提交 PR。

## CLI 调用

共享文件系统：

```bash
python cli.py /path/to/image.png "What is left of the button?"
```

不共享文件系统：

```json
{
  "protocol": 1,
  "image": {"b64": "<base64>", "ext": ".png"},
  "question": "What is left of the button?",
  "options": {"max_objects": 16}
}
```

stdout 只有一个 JSON 对象。Bridge 逻辑：

- `ok`：把 `context` 交给 Agent；
- `unavailable`：按稳定的 `unavailable.reason` 回退或明确告知不可见，不猜图；
- `error`：向宿主暴露 `error.code` 和 `error.message`，不要盲目重试。

退出码不能替代 `status`，因为 `ok` 与 `unavailable` 都是退出码 0。

## 只读握手

安装或 CI 可以先验证：

```bash
python cli.py --self-check
python cli.py --protocol-version
```

两条命令都不读取图片、不使用 Token、不访问网络。无 Key 时 `--self-check`
返回 `unavailable / no_api_key` 且退出码为 0，这是正常结果。

## 模板文件

| 文件 | 用途 |
|---|---|
| `adapter.py` | Python 参考实现：spawn → parse → status mapping |
| `smoke_test.py` | 离线验证状态映射 |
| `README.md` | 本说明；复制后替换成目标 Agent 的真实文档 |

完整贡献规则见 [CONTRIBUTING.md](../../CONTRIBUTING.md)。
