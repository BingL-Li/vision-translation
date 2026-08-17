# Changelog

All notable changes to the `vision-translation-dsh` native dsh adapter.

## [0.2.0] — 2026-08-17

### Fixed

- **Bundled Python core** (`python/` in the tarball): `prepack` hook
  (`scripts/bundle-core.sh`) copies `cli.py` + `vision_translation.py` into
  the package, and `resolveCli` now finds the bundled CLI out of the box —
  a fresh `npm install` no longer throws `CliMissingError` (npm supply-chain
  audit finding, high).
- **Tightened release tag rule**: `publish-dsh.yml` now triggers only on
  semantic-version tags (`v[0-9]+.[0-9]+.[0-9]+`), not any `v*`.
- **Pinned Actions SHAs**: `actions/checkout` / `actions/setup-node` pinned
  to their v4 tag commit SHAs.

### Added

- **Pre-publish isolated smoke test** (`scripts/pre-publish-smoke.sh`,
  `npm run smoke`): packs the real tarball, installs into a clean temp dir,
  asserts the bundled Python core, and probes `resolveCli` with no config —
  wired into the publish workflow before `npm publish`.
- The bundled core includes the VLM endpoint configuration (OpenAI-compatible
  base URL / API key env vars), so the npm package inherits it.

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
- Official discoverability tags: npm `keywords` now include `dsh-plugin` /
  `deepseek-harness-plugin` / `cordis-plugin`, and the README documents the
  `dsh-plugin` GitHub topic for the official dsh plugin registry.
