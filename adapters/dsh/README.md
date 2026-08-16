# vision-translation-dsh — native dsh adapter

A **native [dsh](https://github.com/deepseek-ai/deepseek-harness) (DeepSeek
Harness) Cordis plugin** that lets any dsh profile ground images through the
[vision-translation](../../README.md) pipeline. It registers one tool,
`vision_translate`, and returns a structured `<vision-context>` block that
the main model reasons over.

> Chosen npm package name: **`vision-translation-dsh`** (checked free on the
> npm registry at implementation time via `npm view vision-translation-dsh`).
> This adapter lives in the repo at [`adapters/dsh/`](.). For an MCP-based
> alternative see [`adapters/mcp/`](../mcp/).

## Discoverability (official dsh plugin tag)

Per the [dsh README](https://github.com/deepseek-ai/deepseek-harness),
plugin repos get discovered through the **`dsh-plugin`** topic and the npm
`keywords` of the published package. This adapter ships the required tags:

- GitHub topic: `dsh-plugin` (add it on the repository's About/Topics page).
- npm `keywords`: `dsh`, `dsh-plugin`, `deepseek-harness`,
  `deepseek-harness-plugin`, `cordis`, `cordis-plugin`, `vision`,
  `vision-translation`, `visual-primitives`, `mcp`, `grounding`.

The dsh profile installs the plugin by package name (`vision-translation-dsh`)
via the [bundle patch](#install), so discoverability does not affect the
plugin id or tool id (`vision-translate`).

## How it works

The plugin is the thin non-Python shell the architecture prescribes
([ADAPTERS.md](../../ADAPTERS.md), [CONTRIBUTING.md](../../CONTRIBUTING.md)):

```
dsh agent ──tools──▶ vision_translate(image, question?, model?, max_objects?)
                          │  (uses the dsh attachment ref directly)
                          ▼
                    spawn `python cli.py`  (PROTOCOL v1 stdin envelope)
                          │  b64 envelope (attachment) or image.path
                          ▼
                    core (vision_translation.py) → <vision-context>
```

**Key difference vs the MCP preset:** the dsh Web UI hands images to the model
as `ImageBlock` attachments — an opaque `sha256:<hex>` reference, not a file
path. A stdio MCP tool can only ever receive strings, so the MCP path cannot
see Web-uploaded images. This **native plugin resolves the ref through
`ctx.attachments.readImage`** and ships the bytes to the CLI over a stdin b64
envelope — no shared filesystem required. This is the host integration the
ADAPTERS.md registry marks as the native-plugin trigger.

## Install

With a dsh workspace, add the package as a profile dependency and merge the
bundle patch:

```bash
npm add vision-translation-dsh          # or pnpm add / yarn add
```

Then append the `- insert:` block from [`cordis.patch.yml`](cordis.patch.yml)
to your profile's `cordis.patch.yml` (e.g. `~/.dsh/profiles/web/cordis.patch.yml`)
or mount it as a deployment bundle patch. The block registers the plugin row
`id: vision-translate` for the `vision-translation-dsh` package.

Zero runtime dependencies; the only peer packages are dsh's
`@deepseek-ai/dsh-tools` and `@deepseek-ai/dsh-attachment`, which any dsh
profile already provides.

## Profile configuration

| config key | default | meaning |
|---|---|---|
| `cliPath` | `""` (auto) | Absolute path to `cli.py`. Resolution order: `cliPath` → env `VISION_TRANSLATION_CLI` → package-relative `../../cli.py` (in-repo `adapters/dsh` layout). |
| `pythonBin` | `"python3"` | Python binary used to run `cli.py`. |
| `toolCallTimeoutMs` | `120000` | Cooperative tool-call timeout; also the CLI kill timer. |

Merging via the bundle patch:

```yaml
- insert:
    - id: vision-translate
      name: vision-translation-dsh
      config:
        cliPath: ""            # "" = auto-detect
        pythonBin: "python3"
        toolCallTimeoutMs: 120000
```

## Tool usage

`vision_translate(image, question?, model?, max_objects?)`

- `image` — **required**. A local absolute/relative file path **or** a dsh
  image attachment reference (`sha256:<hex>` / `attachment:sha256:<hex>`).
- `question` — optional guiding question for the parse focus.
- `model` — optional auxiliary VLM override (empty → the CLI's default chain).
- `max_objects` — optional primitive cap (`1..16`, default 16, clamped).

Returned value is a string: the `<vision-context>` text when vision succeeded,
or an explicit **`vision unavailable (reason: …)`** message when it could not
produce context (no key, VLM down, …). When the result says vision is
unavailable, tell the user you cannot see the image — do not guess or
fabricate it. `error` states surface as a failed tool call.

## Comparing with the MCP preset

| axis | MCP preset (`adapters/mcp/`) | native plugin (this adapter) |
|---|---|---|
| image input | local file path only | file path **or** dsh attachment ref (Web uploads work) |
| process | one stdio MCP server per host | spawns `python cli.py` per call only; no server |
| lifecycle | long-lived server process | Cordis plugin, HMR with the profile |
| bytes | CLI reads the file | b64 stdin envelope for attach-ments; path for files |
| deps | `mcp` + venv | zero runtime deps (peer-only) |

## Privacy

- Images are sent to the configured **OpenRouter auxiliary VLM** (default
  `xiaomi/mimo-v2.5`) by the Python core. See
  [`vision_translation.py`](../../vision_translation.py).
- The **API key is never hardcoded or read by this plugin**. The CLI resolves
  it itself, in order: process env `OPENROUTER_API_KEY`, `~/.hermes/.env`,
  or `~/.env` (see `cli._ensure_key` / PROTOCOL.md).
- **No image bytes, OCR text, or full request is written to logs.**

## Development / test

Node ≥ 20 required (uses `node:test`). Tests are offline and dependency-free:

```bash
cd adapters/dsh
npm test        # = node --test "tests/**/*.test.js" (Node ≥ 20 built-in glob)
```

`npm pack --dry-run` verifies the publishable tarball (only `lib/`,
`cordis.patch.yml`, `README.md` `package.json` contents).

## License

MIT © 2026 Binglun Li. See [`LICENSE`](LICENSE).
