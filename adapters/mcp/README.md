# MCP adapter — universal bridge for any MCP host

Exposes the core as a single MCP tool, `vision_translate`, over stdio. Any
MCP-capable agent — **dsh, Claude Code, Cursor, Hermes, Codex, …** — can
ground images through it without knowing anything about Python.

The server imports the core directly (`vision_translation.py`) and reuses the
CLI's status classification (`cli._classify`), so it never forks logic
(iron rule: import, don't re-implement — see
[CONTRIBUTING.md](../../CONTRIBUTING.md)).

Protocol semantics are preserved:

| state | MCP mapping |
|---|---|
| `ok` | normal result: `<vision-context>` text |
| `unavailable` | **normal result** with an explicit `vision unavailable (reason: …)` message — fail-closed is legal, the model must not guess or fabricate image content |
| `error` | MCP error (`isError`) — a broken call, safe to retry |

## Install

The adapter needs the `mcp` package (the core itself stays zero-dependency):

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> **Why `<2.0`?** mcp 2.0.0 removed the high-level `mcp.server.fastmcp`
> (FastMCP) API this server is built on. The pin keeps installs on the
> stable 1.x line; revisit once the 2.x high-level API stabilises.

Verify offline (mock VLM, no key, no network):

```bash
.venv/bin/python smoke_test.py
```

## Run

```bash
.venv/bin/python server.py    # stdio transport; stdout is JSON-RPC
```

## Wire it up

### dsh (official preset)

dsh ships a native MCP client (`@deepseek-ai/dsh-mcp-client`). Merge the
`- insert:` block from [`dsh-preset.yml`](dsh-preset.yml) into your profile's
`cordis.patch.yml` (e.g. `~/.dsh/profiles/web/cordis.patch.yml`), adjusting
paths. The model sees `mcp__vision__vision_translate`.

### Claude Code

`.mcp.json` at your project root:

```json
{
  "mcpServers": {
    "vision": {
      "command": "/abs/path/to/vision-translation/adapters/mcp/.venv/bin/python",
      "args": ["/abs/path/to/vision-translation/adapters/mcp/server.py"],
      "env": { "OPENROUTER_API_KEY": "sk-..." }
    }
  }
}
```

### Cursor

Same shape in `~/.cursor/mcp.json`.

### Hermes

Hermes has both a native plugin (recommended — in-process, no subprocess) and
an MCP client. Use one or the other, not both:

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  vision:
    command: /abs/path/to/vision-translation/adapters/mcp/.venv/bin/python
    args: [/abs/path/to/vision-translation/adapters/mcp/server.py]
    env:
      OPENROUTER_API_KEY: "sk-..."
```

Tool name: `mcp_vision_vision_translate`.

## Notes

- stdio MCP servers are long-lived processes: the Python cold start is paid
  once per host session, not once per call.
- Keep stdout pure — the server never prints to stdout; logs go to stderr.
- The image is passed as a **local file path**. Hosts that only hand you
  blobs or attachments (no shared filesystem) need a native adapter — dsh
  attachment support is an open question, see [ADAPTERS.md](../../ADAPTERS.md).
