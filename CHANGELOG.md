# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/).

## [Unreleased]

### Added

- **MCP adapter** (`adapters/mcp/`): universal stdio server exposing the
  core as one `vision_translate` MCP tool. Works with any MCP host (dsh,
  Claude Code, Cursor, Hermes, …). Imports the core directly and reuses
  `cli._classify`, so it never forks logic; `unavailable` stays a normal
  (non-error) result so hosts treat fail-closed as legal, not retryable.
  Offline smoke test (`smoke_test.py`, mock VLM, no key/network) + README
  with wiring configs for dsh / Claude Code / Cursor / Hermes.
- **dsh official preset** (`adapters/mcp/dsh-preset.yml`): `- insert:` block
  wiring the MCP server into a dsh profile via the native
  `@deepseek-ai/dsh-mcp-client` (model sees `mcp__vision__vision_translate`).
  Native Cordis plugin remains an open question (attachment parsing / rich
  rendering / lifecycle), tracked in ADAPTERS.md.

### Changed

- `ADAPTERS.md`: registry now lists mcp (official) + dsh preset; dsh native
  plugin listed as open question instead of planned.
- CI: MCP adapter smoke test added to the workflow.
- `adapters/mcp/requirements.txt`: pinned to `mcp>=1.0,<2.0` — mcp 2.0.0
  removed the FastMCP API (`mcp.server.fastmcp`) this server uses.

## [0.2.0] — 2026-08-15

### Added

- **CLI protocol bridge** (`cli.py`, PROTOCOL v1): cross-language contract
  so any agent (dsh, Claude Code, aider, …) can reach the core by spawning
  the CLI and speaking JSON. Stdout carries exactly one JSON object; status
  is `ok` / `unavailable` (fail-closed, exit 0) / `error` (exit 1–2);
  `unavailable` carries a stable `reason`. Input via argv path **or** stdin
  JSON envelope (base64 image, for containers / remote agents).
- **Read-only handshake commands**: `cli.py --self-check` and
  `cli.py --protocol-version` (no tokens, no network, safe for CI).
- **Offline test suite** (`tests/`): core unit tests + CLI protocol tests,
  VLM mocked at the HTTP boundary — no API key, no paid requests
  (28 tests).
- **Adapter template** (`adapters/_template/`): scaffold for new adapters
  (spawn → parse → branch on status) + smoke test.
- **`ADAPTERS.md`** — adapter registry and ecosystem rules.
- **`CONTRIBUTING.md`** — two-tier review bar (core high, adapters low) and
  the iron rule: adapters never re-implement core logic.
- **`PROTOCOL.md`** — normative single source for the protocol.
- **GitHub Actions CI** (`.github/workflows/ci.yml`): pytest across Python
  3.10–3.12, template smoke test, CLI stdout purity, version consistency
  check (`cli.CORE_VERSION` == `plugin.yaml` `version`). No API keys in CI.
- `pyproject.toml` (pytest `pythonpath` only; no runtime deps).

### Changed

- `plugin.yaml` `version` 0.1.0 → 0.2.0.
- `__init__.py`: dual-mode import (package-relative for Hermes, bare
  top-level fallback for pytest collection) so tests can run against the
  hyphenated plugin directory name.
- README: CLI protocol documented; project layout added.

### Fixed

- None.

## [0.1.0] — 2026-08-14

### Added

- Initial release: `Translation with Visual Primitives` Hermes plugin
  (`vision_translation.py` core + `vision_translate` tool). Image →
  auxiliary VLM structured JSON → canonical `norm-1000 xyxy` primitives →
  programmatic spatial relations → `<vision-context>` text, injected for
  text-only main models.
- `demos/vision_translate_demo.py`: end-to-end CLI demo (includes a
  text-LLM step for illustration; production integrations use `cli.py`).
- Code-review pass (same day): dead code removal, out-of-contract warning
  path, English-only module (VLM prompt excepted).
