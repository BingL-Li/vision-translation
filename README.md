# Translation with Visual Primitives

> **一个视觉翻译核心，任何 agent 的即插即用转接器。**
>
> An image → `<vision-context>` translator: a pure Python core turns an
> image into structured **visual primitives** (norm-1000 xyxy bboxes),
> **spatial relations** (derived from geometry), and **OCR** — then hands
> the result to your text-only model as text. Your main model never touches
> pixels; something else does the seeing.

The name is a deliberate counterpoint to DeepSeek's paper
[*Thinking with Visual Primitives*](https://arxiv.org/abs/2508.12952): that
paper makes a model *think in* visual primitives internally; this project
does the opposite — an external layer **translates** vision into primitives
and injects them as text, leaving your main model untouched.

```
┌─────────┐   ┌──────────────────┐   ┌───────────────────────────┐
│  image  │ → │ auxiliary VLM    │ → │ canonical primitives      │
│ (file)  │   │ (any, model-     │   │ norm-1000 xyxy bboxes     │
└─────────┘   │  agnostic)       │   ├───────────────────────────┤
              └──────────────────┘   │ programmatic spatial      │
                                     │ relations (geometry)      │
                                     ├───────────────────────────┤
                                     │ <vision-context> text     │
                                     │ → injected into the main  │
                                     │   text-only LLM           │
                                     └───────────────────────────┘
```

## Architecture: core + protocol + adapters

```
vision_translation.py   ← core: the ONLY intelligence (import-pure, stdlib-only)
cli.py                  ← protocol bridge: image → JSON (PROTOCOL v1)
adapters/               ← thin shells: Hermes, dsh, Claude Code, your agent…
```

- **core** never knows about agents — it only does `image → <vision-context>`.
- **cli.py** is the only cross-language contract: any adapter in any
  language spawns it and speaks JSON ([PROTOCOL.md](PROTOCOL.md)).
- **adapters** are thin shells; they never re-implement core logic
  ([ADAPTERS.md](ADAPTERS.md), [CONTRIBUTING.md](CONTRIBUTING.md)).

## Quick start

### As a CLI (anyone, no Hermes needed)

```bash
export OPENROUTER_API_KEY=sk-...
python cli.py path/to/image.jpg "What is the layout?"
```

stdout is exactly one JSON object (logs go to stderr):

```json
{"protocol": 1, "core_version": "<core_version>", "status": "ok",
 "context": "<vision-context>…</vision-context>",
 "model": "xiaomi/mimo-v2.5"}
```

> `<core_version>` is a placeholder — the authoritative value comes from
> `python cli.py --protocol-version` (and is kept in sync with
> `plugin.yaml` by CI).

Status is `ok` | `unavailable` (fail-closed, exit 0) | `error` (exit 1–2).
Full spec: [PROTOCOL.md](PROTOCOL.md).

Read-only handshake commands (no tokens, no network — safe for CI):

```bash
python cli.py --self-check
python cli.py --protocol-version
```

### As a Hermes Agent plugin

Requires Hermes Agent with a configured `OPENROUTER_API_KEY`.

```bash
# From GitHub (recommended)
hermes plugins install BingL-Li/vision-translation --enable

# Or manually: clone/copy into the user plugin directory
git clone https://github.com/BingL-Li/vision-translation ~/.hermes/plugins/vision-translation
hermes plugins enable vision-translation
```

Then **restart** the Hermes process serving your conversation (a new CLI
session or a gateway restart — plugins load at process start).

Verify:

```bash
hermes plugins list          # shows enabled
hermes tools list            # shows ✓ enabled vision_translation
```

The tool `vision_translate` (toolset `vision_translation`) accepts:

| param          | type   | description                                            |
|----------------|--------|--------------------------------------------------------|
| `image_path`   | string | local image path (required)                            |
| `question`     | string | optional question to guide parsing                     |
| `max_objects`  | int    | max primitives to keep (default 12, cap 16)            |

**When to use `vision_translate` vs the built-in `vision_analyze`:**

| need                                     | tool                        |
|------------------------------------------|-----------------------------|
| one-line description, cheap & fast       | `vision_analyze`            |
| coordinates, counting, "who is left of whom", UI/PCB element locations, structured entities, OCR | `vision_translate` |

### As your own agent's adapter

Copy `adapters/_template/`, write a thin shell that spawns `cli.py` and
branches on `status`, add a smoke test, open a PR. Walkthrough:
[ADAPTERS.md](ADAPTERS.md) → [CONTRIBUTING.md](CONTRIBUTING.md).

## Features

- **Model-agnostic vision bridge** — works with *any* auxiliary VLM on
  OpenRouter (default: `xiaomi/mimo-v2.5`; override with
  `VISION_TRANSLATE_VLM`). Your main model stays text-only and unchanged.
- **Structured, not descriptive** — object bounding boxes in a canonical
  `norm-1000 xyxy` coordinate contract, spatial relations
  (`left_of / right_of / above / below / inside / overlaps`) derived
  *programmatically* from geometry (`source: geometry`), plus OCR and a
  scene summary.
- **Zero heavy dependencies** — pure Python stdlib (`urllib`); Pillow is
  optional (used only for EXIF orientation + downscaling).
- **Fail-closed, honest grounding** — on repeated invalid VLM output the
  CLI returns an explicit `status: "unavailable"` payload instead of
  injecting fabricated context. Every primitive is annotated
  `grounding: prompted` (coordinates are prompted from the VLM, not native
  detector output).
- **Import-pure core** — `vision_translation.py` is a side-effect-free pure
  function library (no argparse, no network at import, no prints), so it is
  unit-testable and safe to import anywhere.
- **One protocol, many agents** — the CLI contract is versioned
  (`protocol` + `core_version`), forward-compatible, and documented once in
  [PROTOCOL.md](PROTOCOL.md). Adapters declare compatibility.

## Project layout

```
vision_translation.py   ← core: the ONLY intelligence (import-pure, stdlib-only)
cli.py                  ← protocol bridge: image → JSON (PROTOCOL v1)
__init__.py             ← Hermes plugin (in-process adapter, repo root)
adapters/_template/     ← scaffold for new adapters (any language/agent)
tests/                  ← offline core + protocol tests (mock VLM, no keys)
PROTOCOL.md             ← normative CLI protocol spec (single source of truth)
ADAPTERS.md             ← adapter registry + ecosystem rules
CONTRIBUTING.md         ← contribution rules (core = high bar, adapters = low)
CHANGELOG.md            ← version history
```

## Demo (end-to-end pipeline)

```bash
python demos/vision_translate_demo.py path/to/image.jpg "What is the layout?"
```

Shows the full pipeline including a text-LLM step (demo only; production
integrations use `cli.py`).

## Design notes

- **Coordinate contract**: `norm-1000` — image space normalized to 1000×1000,
  `xyxy` box order, clamped/validated on the way in; zero-area boxes are
  dropped.
- **Spatial relations** are derived from geometry with a small epsilon
  (`EPS=20/1000`), deduplicated, and contradiction-free by construction
  (directional predicates only fire when boxes are strictly separated).
- **Budget**: results are hard-capped (`RESULT_BUDGET=2000` chars);
  primitives/relations survive, prose is trimmed.
- **Out-of-contract detection**: if the VLM returns boxes outside the
  `norm-1000` range (e.g. raw pixel coordinates), they are clamped and a
  `vision_warnings:` line is emitted into the context so the main model knows
  the numbers may be unreliable.
- **Cost note**: the fail-closed path can spend up to 3 full image-bearing
  VLM calls before giving up (each retry re-sends the image). This is
  deliberate — a wrong context is worse than an explicit `unavailable` —
  but be aware that a failing VLM is not cheap.
- **Security**: images are sent to the configured OpenRouter VLM only. The
  tool never fabricates coordinates — if the VLM fails, you get an explicit
  error, not a guess.

## Limitations

- Grounding is *prompted*: the auxiliary VLM is prompted to emit boxes; it
  is not a native detection model. Accuracy is good for layout/UI/scene
  understanding but not pixel-perfect.
- Requires an OpenRouter-capable auxiliary VLM that accepts image input
  (check `input_modalities` before choosing).
- Main-model benefits are best for models with strong spatial reasoning
  over coordinate text (DeepSeek-family models were the original target).

## Development history

This project was not designed top-down; it grew out of one paper, a stretch
of reading other people's code, and a stubborn idea that refused to go
away.

**10 Jul 2026 — the idea.** I read *Thinking with Visual Primitives*. The
part that stuck with me was not the architecture but the representation: an
image does not have to reach a model as pixels or as prose. It can reach it
as a small set of *primitives* — labelled boxes in a canonical coordinate
space — and a model can reason over those primitives the way it reasons over
any other structured text. The paper puts that representation *inside* the
model. My first thought was the inversion: if primitives are just text, the
translation step can live entirely *outside* the model. A text-only main
model would never need to change; something else does the seeing and hands
it a `<vision-context>`. That inversion is where the project's name comes
from.

**Jul 2026 — research.** Before writing anything, I went looking for prior
art, and found that the same idea had already been realised in the open: the
**OpenHanako** agent ships a `core/vision-bridge.ts` that turns an image into
a `<vision-context>` block containing `<visual-primitives coord="norm-1000"
box_order="xyxy" grounding="...">`. Reading it saved me from a lot of bad
decisions, and several conventions in this repo are adopted from it on
purpose rather than reinvented:

- the `<vision-context>` / `<visual-primitives>` wire format and the per-line
  `id | type | box | ref | confidence | grounding` layout;
- the `norm-1000` + `xyxy` coordinate contract as the single canonical space;
- the conservative caps (16 primitives, 96-char labels);
- and most importantly the idea of an explicit **grounding mode** — being
  honest about whether coordinates came from a native detector or were merely
  *prompted* out of a VLM. That one line of humility is why this project says
  `grounding: prompted` everywhere instead of pretending to be a detector.

Keeping the format compatible was a deliberate choice: a context block
produced here should be readable by anything that already understands that
convention.

**Jul–Aug 2026 — making it.** Four decisions shaped the implementation,
each one a deliberate narrowing of what the tool is allowed to do:

- *Structure over description.* The output contract is boxes, not prose. A
  rich description reads well and is useless for "which element is left of
  the submit field" — the answer drifts with the phrasing. Coordinates don't.
- *The VLM sees; it does not do geometry.* Asking a VLM for spatial
  relations invites contradictions (A left of B *and* B left of A).
  Relations here are derived programmatically from the boxes
  (`source: geometry`) with an epsilon, so a directional predicate only
  fires when two boxes are strictly separated — contradiction-free by
  construction.
- *No nested reasoning.* The core deliberately never calls a text LLM. It
  returns `<vision-context>` and stops; the main model does the thinking.
  The nested call survives only in `demos/`, to show the pipeline end to
  end.
- *Fail closed.* The worst failure mode is a plausible-looking but empty
  context. On repeated invalid VLM output the tool returns an explicit
  `status: "unavailable"` rather than injecting anything fabricated, and
  out-of-contract boxes surface a `vision_warnings:` line instead of passing
  silently.

Alongside those, `vision_translation.py` was kept as a side-effect-free
pure-function library — no argparse, no network, no prints at import — so
the parsing, normalisation and geometry can be reasoned about and tested
without a plugin host, and so the CLI and every adapter can reuse the exact
core instead of a copy of it.

**14 Aug 2026 — release.** Published as a Hermes Agent plugin (`0.1.0`),
followed the same day by a code-review pass that removed dead code, added
the out-of-contract warning path, and made the module English-only apart
from the VLM prompt.

**15 Aug 2026 — core + adapters.** Added the cross-language CLI protocol
(`cli.py`, PROTOCOL v1), an offline test suite, the adapter template,
ecosystem docs, and CI. The repo stopped being "a Hermes plugin" and became
"a core + a protocol + a ring of adapters" — Hermes remains the in-process
official adapter at the repo root, unchanged.

## Acknowledgements

- To the authors of *Thinking with Visual Primitives* — for the
  representation this whole project is built on. The direction here is
  inverted, but the idea is theirs.
- To the authors and contributors of
  **[OpenHanako](https://github.com/liliMozi/openhanako)**, and specifically
  to whoever wrote and maintains `core/vision-bridge.ts` — seeing the same
  idea already working in the open was genuinely helpful. The context
  format, the coordinate contract and the grounding-mode honesty in this
  repo come from reading your work. Thank you.
- To Nous Research, for the Hermes Agent plugin system the repo-root adapter
  is built on.

Any mistakes in the implementation are mine, not theirs.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) (two-tier review bar: core = high,
adapters = low) and [ADAPTERS.md](ADAPTERS.md) (registry + rules). Changes
are documented in [CHANGELOG.md](CHANGELOG.md).

## License

MIT © 2026 Binglun Li. Built as a Hermes Agent plugin with Nous Research's
Hermes Agent.
