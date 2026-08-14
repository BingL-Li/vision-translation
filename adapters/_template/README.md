# Adapter Template — vision-translation

This is the **scaffold for new adapters**. The goal: a thin shell that
gives your agent/your language vision by talking to the core CLI — nothing
more.

## The ONLY rule

> **Adapters never copy core logic.** No re-implementing the prompt, the
> JSON parsing, bbox normalization, or VLM calls in your language. The core
> is the single source of truth; the CLI is the single cross-language
> contract (see [PROTOCOL.md](../../PROTOCOL.md)). If spawn overhead bothers
> you, open an issue — we optimize the CLI cold start. Do not fork the
> logic.

## Add a new adapter in 5 steps

1. **Copy this directory** → `adapters/<your-adapter>/`
   (e.g. `adapters/dsh/`, `adapters/claude-code/`).
2. **Write the thin shell** — in your language:
   - spawn `python cli.py <image_path> ["question"]`, or pass a stdin JSON
     envelope when the image is not on a shared filesystem
     (`{"protocol":1,"image":{"b64":"…","ext":".png"},"question":"…"}`);
   - `JSON.parse(stdout)` — stdout is exactly one JSON object, nothing else;
   - branch on `status`:
     - `ok` → hand the `context` (`<vision-context>` text) to your agent;
     - `unavailable` → retry/fallback (reason tells you why);
     - `error` → surface it, do not retry blindly.
   - The reference is `adapters/_template/adapter.py` (Python).
3. **Write a README.md** — what it does, install/use instructions, which
   protocol it speaks.
4. **Write a smoke test** — offline, no API key. Prove your adapter maps
   the statuses correctly (see `smoke_test.py`).
5. **Open a PR** — add yourself to the registry table in
   [ADAPTERS.md](../../ADAPTERS.md) and follow
   [CONTRIBUTING.md](../../CONTRIBUTING.md). CI runs the core + protocol
   tests and your smoke test.

## Protocol quick reference

Read [PROTOCOL.md](../../PROTOCOL.md) — it is the single source of truth.
Key points:

- `python cli.py --self-check` and `--protocol-version` are read-only, no
  tokens, no network — safe for CI handshakes.
- `unavailable` is a **legal** result (exit 0): no key, VLM down, invalid
  VLM output. Distinguish it from `error` (malformed request, exit 1–2).
- Prefer `unavailable.reason` over `message` for logic.

## What this template contains

| file         | purpose                                                       |
|--------------|---------------------------------------------------------------|
| `adapter.py` | minimal Python adapter: spawn → parse → branch (rename per language) |
| `smoke_test.py` | offline test: adapter maps protocol statuses correctly     |
