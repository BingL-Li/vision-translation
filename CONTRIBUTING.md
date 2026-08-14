# Contributing to vision-translation

Thanks for wanting to help! This project is deliberately small: **one pure
core + one CLI protocol + a ring of thin adapters**. The contribution rules
below exist to keep it that way.

## The architecture in one paragraph

```
vision_translation.py   ← core: the ONLY intelligence (import-pure, stdlib-only)
cli.py                  ← protocol bridge: image → JSON, stdout-only
adapters/               ← thin shells for any agent/language
tests/                  ← core + protocol tests (offline, mock VLM)
```

- **core** never knows about agents. It does `image → <vision-context>`.
- **cli.py** is the only cross-language contract (PROTOCOL v1).
- **adapters** are thin shells that talk to the CLI. They never hold logic.

## The two-tier review bar

| change | bar |
|--------|-----|
| **core** (`vision_translation.py`) | HIGH — API changes need maintainer discussion. This is the heart; a bad change breaks every adapter. |
| **adapters** | LOW — thin shell + smoke test that passes. Community adapters are self-maintained (listed in ADAPTERS.md). |

## The iron rule

> **Adapters never copy core logic.** No re-implementing the prompt, the
> tolerant JSON parsing, bbox normalization, spatial relations, or VLM
> calls — in any language.

**Why:** the moment an adapter forks the parsing, the ecosystem forks with
it and every adapter starts disagreeing about coordinates. If spawn overhead
bothers you, open an issue and we make the CLI faster (lazy imports, faster
startup) — that's the fix, not a rewrite.

## Getting started

1. Fork the repo, `git clone` your fork.
2. `cd vision-translation && python -m pytest tests/` — core + protocol
   tests run offline (no API key needed, VLM is mocked).
3. For a live end-to-end check: `export OPENROUTER_API_KEY=…` then
   `python cli.py path/to/image.jpg "what's the layout?"`.

## Adding an adapter

1. Copy `adapters/_template/` → `adapters/<your-adapter>/`.
2. Write the thin shell (spawn CLI → parse JSON → branch on status).
3. Write a README (what it does, how to install/use) + a smoke test.
4. Add yourself to the registry table in `ADAPTERS.md`.
5. Open a PR — CI runs core + protocol tests + every adapter's smoke test.

## CI

`.github/workflows/ci.yml` runs on every PR:

- `pytest tests/` (offline: core unit tests + protocol tests, VLM mocked)
- template adapter smoke test
- version consistency check: `cli.py`'s `CORE_VERSION` == `plugin.yaml`'s `version`

**No API keys in CI.** The workflow never injects `OPENROUTER_API_KEY`;
tests assert that without a key, `--self-check` returns
`status: unavailable, reason: no_api_key` with exit 0. This is both
documentation and a regression guard.

## Changing the core

1. Open an issue first — describe the behavioural change and why adapters
   need it.
2. Keep `analyze()` import-pure: no argparse, no network at import, no
   prints.
3. Bump `core_version` in `cli.py` AND `version` in `plugin.yaml` together
   (CI checks they match).
4. A breaking protocol change bumps the `protocol` number and the repo major
   version — adapters declare compatibility.

## Code style

- Python 3.9+ compatible, stdlib-only core (Pillow optional for
  downscaling).
- No prints in core. Logs in CLI go to stderr. stdout is JSON-only.
- Type hints on public functions; docstrings explain *contracts* (what's
  guaranteed), not just *what*.

## License

MIT © 2026 Binglun Li. By contributing you agree your work is licensed under
the same terms.
