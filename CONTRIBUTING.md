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
PROTOCOL.md             ← normative CLI protocol spec (single source of truth)
```

- **core** never knows about agents. It does `image → <vision-context>`.
- **cli.py** implements the protocol; **PROTOCOL.md** is its normative spec.
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

## Protocol changes

The protocol is specified **once**, in `PROTOCOL.md`; `cli.py` implements
it. When changing the protocol:

1. Edit **PROTOCOL.md first** — it is the source of truth.
2. Implement the change in `cli.py`, keeping the docstring brief and
   pointing at PROTOCOL.md.
3. Bump `core_version` in `cli.py` AND `version` in `plugin.yaml` together
   (CI asserts they match).
4. A breaking protocol change bumps the `protocol` number and the repo major
   version — adapters declare compatibility.
5. Update `ADAPTERS.md` / `_template/README.md` only where they reference
   protocol details; prefer linking to PROTOCOL.md over repeating it.

## Getting started

1. Fork the repo, `git clone` your fork.
2. `cd vision-translation && python -m pytest` — core + protocol tests run
   offline (no API key needed, VLM is mocked).
3. For a live end-to-end check: `export OPENROUTER_API_KEY=…` then
   `python cli.py path/to/image.jpg "what's the layout?"`.

> **Known pitfall — pytest + the hyphenated repo root.** The repo root is
> the Hermes plugin package: its directory name (`vision-translation`)
> contains a hyphen and its `__init__.py` uses a **dual-mode import** (try
> relative, fall back to absolute) so pytest can collect tests without
> tripping over the hyphen. Do **not** "simplify" that `try/except ImportError`
> back to a bare `from . import …` — deleting the fallback breaks the test
> suite (CollectError: "attempted relative import with no known parent
> package"). If you think it looks redundant, run `python -m pytest` first.

## Adding an adapter

1. Copy `adapters/_template/` → `adapters/<your-adapter>/`.
2. Write the thin shell (spawn CLI → parse JSON → branch on status).
3. Write a README (what it does, how to install/use) + a smoke test.
4. Add yourself to the registry table in `ADAPTERS.md`.
5. Open a PR — CI runs core + protocol tests + the template smoke test.
   (CI does not auto-discover new adapters; wire your adapter's smoke test
   into the workflow explicitly, or rely on the template smoke test to guard
   the protocol.)

## PR checklist

- [ ] No core logic copied into an adapter (iron rule).
- [ ] `python -m pytest` passes locally (offline, no API key).
- [ ] Smoke test for new adapters.
- [ ] `ADAPTERS.md` registry updated (if adding an adapter).
- [ ] Version bumps done together: `cli.py` `CORE_VERSION` == `plugin.yaml`
      `version` (CI checks).
- [ ] Protocol changes: PROTOCOL.md updated first, docstring kept brief.
- [ ] New/changed CLI behaviour: stdout stays pure JSON, statuses documented.

## CI

`.github/workflows/ci.yml` runs on every PR (Python 3.10 / 3.11 / 3.12):

- `pytest` (offline: core unit tests + protocol tests, VLM mocked)
- template adapter smoke test
- CLI stdout purity check (`--self-check` / `--protocol-version` parse as
  single JSON objects)
- version consistency check: `cli.py`'s `CORE_VERSION` == `plugin.yaml`'s
  `version`

**No API keys in CI.** The workflow never injects `OPENROUTER_API_KEY`;
tests assert that without a key, `--self-check` returns
`status: unavailable, reason: no_api_key` with exit 0. This is both
documentation and a regression guard.

## Changing the core

1. Open an issue first — describe the behavioural change and why adapters
   need it.
2. Keep `analyze()` import-pure: no argparse, no network at import, no
   prints.
3. Bump versions together (see Protocol changes, step 3).
4. Keep the `<vision-context>` wire format compatible unless the change is
   explicitly breaking and discussed.

## Code style

- Python 3.9+ compatible core (stdlib-only; Pillow optional for
  downscaling). Tests run on 3.10+ (pytest 9 requirement).
- No prints in core. Logs in CLI go to stderr. stdout is JSON-only.
- Type hints on public functions; docstrings explain *contracts* (what's
  guaranteed), not just *what*.

## License

MIT © 2026 Binglun Li. By contributing you agree your work is licensed under
the same terms.
