# Changelog

All notable changes to the `vision-translation-dsh` native dsh adapter.

## [0.1.0] — 2026-08-15

### Added

- Native dsh (DeepSeek Harness) Cordis plugin adapter: registers the dsh tool
  `vision_translate`, grounding images into `<vision-context>` via the Python
  CLI (`cli.py`, PROTOCOL v1) — never re-implements core logic.
- dsh attachment support (`sha256:<hex>` / `attachment:sha256:<hex>`) resolved
  through `ctx.attachments.readImage` into a stdin b64 envelope, bringing
  Web-UI image uploads to the tool (the path the MCP preset cannot take).
- Three-state PROTOCOL mapping: `ok` → `<vision-context>`; `unavailable` →
  normal fail-closed "do not guess" message (never thrown); `error` → thrown
  tool failure. Branching on `status`, not exit code.
- Zero runtime dependencies; peer-only on `@deepseek-ai/dsh-tools` /
  `@deepseek-ai/dsh-attachment`. Offline `node:test` unit tests covering the
  full edge-condition table (attachment refs, paths, malformed refs, ok /
  unavailable / error, timeout, missing CLI, clamping, concurrency-safe).
- Bundle patch (`cordis.patch.yml`) and npm publish metadata
  (`dsh.bundle.patch`, `exports`, `files` whitelist).
