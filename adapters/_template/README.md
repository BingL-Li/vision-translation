# Adapter Template — vision-translation

This is the **scaffold for new adapters**. To add an adapter for your agent
or language:

1. **Copy this directory** → `adapters/<your-adapter>/`
2. Keep the thin shell: talk to `cli.py` over the protocol (below), map
   statuses to your agent's lifecycle, do **not** re-implement parsing.
3. Write your `README.md` (what it does, how to install/use) + a smoke test.
4. Open a PR — CI runs the core tests + protocol tests + your smoke test.

---

## The ONLY rule

> **Adapters never copy core logic.** No re-implementing the prompt, the
> JSON parsing, bbox normalization, or VLM calls in your language. The core
> is the single source of truth; the CLI is the single cross-language
> contract. If spawn overhead bothers you, open an issue — we optimize the
> CLI cold start. Do not fork the logic.

## Talking to the core (PROTOCOL v1)

Any adapter, in any language:

```bash
python cli.py <image_path> ["question"]           # path-based
python cli.py <<'JSON'                             # stdin envelope (b64)
{"protocol": 1, "image": {"b64": "...", "ext": ".png"}, "question": "..."}
JSON
```

**stdout is exactly one JSON object.** Logs go to stderr — `JSON.parse(stdout)`
never sees noise. Branch on `status`, not exit codes:

| status        | meaning                              | exit |
|---------------|--------------------------------------|------|
| `ok`          | vision context produced              | 0    |
| `unavailable` | fail-closed: VLM/key/problem, legal  | 0    |
| `error`       | malformed request / internal bug     | 1–2  |

```json
{"protocol": 1, "core_version": "0.2.0", "status": "ok",
 "context": "<vision-context>…</vision-context>", "model": "xiaomi/mimo-v2.5"}
```

`unavailable` carries `reason` ∈ `{no_api_key, auth, rate_limited, upstream,
vlm_invalid_output, invalid_image, internal}` so the adapter can decide
retry vs. fallback.

**Read-only handshake commands** (no tokens, no network — safe for CI):

```bash
python cli.py --self-check          # {"status":"ok"|"unavailable", "checks":{…}}
python cli.py --protocol-version    # {"protocol":1, "core_version":"0.2.0"}
```

## What this template contains

| file        | purpose                                                      |
|-------------|--------------------------------------------------------------|
| `adapter.py`| minimal Python adapter: spawn → parse → branch (rename per language) |
| `smoke_test.py` | asserts the adapter maps protocol statuses correctly (offline) |

The reference implementation is the Hermes adapter at the **repo root**
(`__init__.py` — in-process `import vision_translation`, no spawn needed).
