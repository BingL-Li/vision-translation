# Adapters — vision-translation ecosystem

`cli.py` is the **only cross-language contract** (see
[PROTOCOL.md](PROTOCOL.md) for the normative spec). Any agent — Hermes,
dsh, Claude Code, aider, anything — gets vision by spawning the CLI and
speaking JSON. Adapters are thin shells; the core holds all the
intelligence.

## How an adapter works

```
agent ──spawn──▶ python cli.py <image> ["question"]
   │                 │
   │                 └─▶ core (vision_translation.py) → <vision-context>
   ▼
JSON.parse(stdout) ──▶ status branch:
   ok           → context is <vision-context> text
   unavailable  → fail-closed (no key / VLM down / invalid output) — legal, exit 0
   error        → malformed request or internal bug — exit 1–2
```

The exact response shapes, `unavailable` reasons, exit-code semantics,
stdin envelope, and versioning rules are defined once, in
[PROTOCOL.md](PROTOCOL.md). Read it before writing an adapter.

New adapter? Copy `adapters/_template/`, write a thin shell + smoke test,
register yourself below, open a PR. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Registry

| adapter | language | target agent | state | maintainer |
|---------|----------|--------------|-------|------------|
| [Hermes](__init__.py) | Python | Hermes Agent plugin | official — in-process (imports core directly, no spawn) | [BingL-Li](https://github.com/BingL-Li) |
| [mcp](adapters/mcp/) | Python | any MCP host: dsh, Claude Code, Cursor, Hermes, Codex… | official — universal stdio server (imports core directly, reuses cli._classify) | [BingL-Li](https://github.com/BingL-Li) |
| [dsh](adapters/mcp/dsh-preset.yml) | — | dsh harness | official preset — wires the MCP adapter into a dsh profile (`cordis.patch.yml` `- insert:` block); native Cordis plugin open question, see below | [BingL-Li](https://github.com/BingL-Li) |
| [_template](adapters/_template/) | Python | any (spawns CLI) | scaffold — copy me | — |

Community adapters are self-maintained: their entry in this table states
who to contact, and CI only smoke-tests them (it does not auto-discover or
run every adapter in the repo).

## Open question — native dsh plugin?

dsh ships a native MCP client, so a Cordis plugin would only earn its
maintenance cost if it adds host-specific value the MCP path can't: parsing
dsh attachments (Web UI uploads may be in-memory blobs, not file paths),
rich UI rendering of `<vision-context>`, or native lifecycle/HMR. Triggers
for building `adapters/dsh/`:

- users report attachments don't reach the MCP tool as file paths, or
- rich rendering / lifecycle integration is actually needed.

Until then the official path is the MCP preset above; new agents should try
MCP first and only write a native adapter when MCP is not enough.

## Rules for adapters

1. **Never re-implement core logic** (prompts, parsing, bbox math, VLM
   calls). The CLI is the single source of truth for non-Python consumers.
2. **stdout must stay pure JSON.** `JSON.parse(stdout)` must always succeed.
   All logs/errors → stderr.
3. **Branch on `status`, not exit codes.** `unavailable` is a legal result
   (exit 0); treat it as a retry/fallback trigger, not a crash.
4. **Prefer the stdin envelope** (`{"protocol":1,"image":{"b64":…}}`) for
   remote/container/agent use where filesystems aren't shared.
5. **Declare your protocol compatibility.** If your adapter needs a newer
   protocol, say so in your README and this table.

## Protocol versioning

The `protocol` field identifies the envelope/response shape (`1` = current).
Breaking changes bump the protocol number and the repo major version; the
single authoritative definition lives in [PROTOCOL.md](PROTOCOL.md).
`core_version` bumps on compatible behaviour changes and is kept in sync
with `plugin.yaml` by CI.

## FAQ

**Why not just import the Python core directly?** Python adapters can
(that's what the Hermes plugin does). Non-Python adapters (TS/Rust/Go)
spawn the CLI — it's the boundary that keeps the core from becoming a
language-specific library.

**Spawn feels slow.** Open an issue — we optimize CLI cold start (lazy
imports). Don't fork the logic.
