# Translation with Visual Primitives

> **Translation with Visual Primitives** — a Hermes Agent native plugin that
> translates an image into a structured, text-only **visual-primitives
> context** (`<vision-context>`), so that text-only main models can *see*
> with coordinates, spatial relations, and OCR — without ever touching pixels.

The name is a deliberate counterpoint to DeepSeek's paper
[*Thinking with Visual Primitives*](https://arxiv.org/abs/2508.12952): that
paper makes a model *think in* visual primitives internally; this plugin does
the opposite — an external layer **translates** vision into primitives and
injects them as text, leaving your main model untouched.

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

## Features

- **Model-agnostic vision bridge** — works with *any* auxiliary VLM on
  OpenRouter (default: `xiaomi/mimo-v2.5`; override with
  `VISION_TRANSLATE_VLM`). Your main model stays text-only and unchanged.
- **Structured, not descriptive** — the tool returns object bounding boxes in
  a canonical `norm-1000 xyxy` coordinate contract, spatial relations
  (`left_of / right_of / above / below / inside / overlaps`) derived
  *programmatically* from geometry (`source: geometry`), plus OCR and a scene
  summary.
- **Zero heavy dependencies** — pure Python stdlib (`urllib`); Pillow is
  optional (used only for EXIF orientation + downscaling).
- **Fail-closed, honest grounding** — on repeated invalid VLM output the tool
  returns an explicit `"status": "unavailable"` payload instead of injecting
  fabricated context. Every primitive is annotated `grounding: prompted`
  (coordinates are prompted from the VLM, not native detector output).
- **Import-pure core** — `vision_translation.py` is a side-effect-free pure
  function library (no argparse, no network at import, no prints), so it is
  unit-testable and safe to import anywhere.

## Development history

This plugin was not designed top-down; it grew out of one paper, a stretch of
reading other people's code, and a stubborn idea that refused to go away.

**10 Jul 2026 — the idea.** I read *Thinking with Visual Primitives*. The part
that stuck with me was not the architecture but the representation: an image
does not have to reach a model as pixels or as prose. It can reach it as a
small set of *primitives* — labelled boxes in a canonical coordinate space —
and a model can reason over those primitives the way it reasons over any other
structured text. The paper puts that representation *inside* the model. My
first thought was the inversion: if primitives are just text, the translation
step can live entirely *outside* the model. A text-only main model would never
need to change; something else does the seeing and hands it a
`<vision-context>`. That inversion is where the project's name comes from.

**Jul 2026 — research.** Before writing anything, I went looking for prior art,
and found that the same idea had already been realised in the open: the
**OpenHanako** agent ships a `core/vision-bridge.ts` that turns an image into a
`<vision-context>` block containing `<visual-primitives coord="norm-1000"
box_order="xyxy" grounding="...">`. Reading it saved me from a lot of bad
decisions, and several conventions in this repo are adopted from it on purpose
rather than reinvented:

- the `<vision-context>` / `<visual-primitives>` wire format and the per-line
  `id | type | box | ref | confidence | grounding` layout;
- the `norm-1000` + `xyxy` coordinate contract as the single canonical space;
- the conservative caps (16 primitives, 96-char labels);
- and most importantly the idea of an explicit **grounding mode** — being
  honest about whether coordinates came from a native detector or were merely
  *prompted* out of a VLM. That one line of humility is why this plugin says
  `grounding: prompted` everywhere instead of pretending to be a detector.

Keeping the format compatible was a deliberate choice: a context block produced
here should be readable by anything that already understands that convention.

**Jul–Aug 2026 — making it.** Four decisions shaped the implementation, each
one a deliberate narrowing of what the tool is allowed to do:

- *Structure over description.* The tool's output contract is boxes, not prose.
  A rich description reads well and is useless for "which element is left of
  the submit field" — the answer drifts with the phrasing. Coordinates don't.
- *The VLM sees; it does not do geometry.* Asking a VLM for spatial relations
  invites contradictions (A left of B **and** B left of A). Relations here are
  derived programmatically from the boxes (`source: geometry`) with an epsilon,
  so a directional predicate only fires when two boxes are strictly separated —
  contradiction-free by construction.
- *No nested reasoning.* The tool deliberately never calls a text LLM. It
  returns `<vision-context>` and stops; the Hermes main model does the
  thinking. The nested call survives only in `demos/`, to show the pipeline
  end to end.
- *Fail closed.* The worst failure mode is a plausible-looking but empty
  context. On repeated invalid VLM output the tool returns an explicit
  `"status": "unavailable"` rather than injecting anything fabricated, and
  out-of-contract boxes surface a `vision_warnings:` line instead of passing
  silently.

Alongside those, `vision_translation.py` was kept as a side-effect-free
pure-function library — no argparse, no network, no prints at import — so the
parsing, normalisation and geometry can be reasoned about and tested without a
plugin host, and so the CLI demo can reuse the exact plugin core instead of a
copy of it.

**14 Aug 2026 — release.** Published as a Hermes Agent plugin (`0.1.0`),
followed the same day by a code-review pass that removed dead code, added the
out-of-contract warning path, and made the module English-only apart from the
VLM prompt.

## Acknowledgements

- To the authors of *Thinking with Visual Primitives* — for the representation
  this whole plugin is built on. The direction here is inverted, but the idea
  is theirs.
- To the authors and contributors of **[OpenHanako](https://github.com/liliMozi/openhanako)**,
  and specifically to whoever wrote and maintains `core/vision-bridge.ts` —
  seeing the same idea already working in the open was genuinely helpful. The
  context format, the coordinate contract and the grounding-mode honesty in
  this repo come from reading your work. Thank you.
- To Nous Research, for the Hermes Agent plugin system this is built on.

Any mistakes in the implementation are mine, not theirs.

## Installation

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

## Usage

The tool `vision_translate` (toolset `vision_translation`) accepts:

| param          | type   | description                                            |
|----------------|--------|--------------------------------------------------------|
| `image_path`   | string | local image path (required)                            |
| `question`     | string | optional question to guide parsing                     |
| `max_objects`  | int    | max primitives to keep (default 12, cap 16)            |

It returns a `<vision-context>` text block — primitives and relations always
come first (protected by a 2000-char budget), prose gets trimmed only when
over budget. No nested text-LLM call: your main model reasons over the
context directly.

**When to use it vs the built-in `vision_analyze`:**

| need                                     | tool                        |
|------------------------------------------|-----------------------------|
| one-line description, cheap & fast       | `vision_analyze`            |
| coordinates, counting, "who is left of whom", UI/PCB element locations, structured entities, OCR | `vision_translate` |

## Demo (CLI, no Hermes needed)

```bash
export OPENROUTER_API_KEY=sk-...
python demos/vision_translate_demo.py path/to/image.jpg "What is the layout?"
```

The demo reuses the exact plugin core, then adds a demo-only step: feeding the
`<vision-context>` to a text-only LLM (default `deepseek/deepseek-v4-flash-0731`,
override with `VISION_TRANSLATE_TEXT`) to show the full pipeline.

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
- **Cost note**: the fail-closed path can spend up to 3 full image-bearing VLM
  calls before giving up (each retry re-sends the image). This is deliberate —
  a wrong context is worse than an explicit `unavailable` — but be aware that
  a failing VLM is not cheap.
- **Security**: images are sent to the configured OpenRouter VLM only. The
  plugin never fabricates coordinates — if the VLM fails, you get an explicit
  error, not a guess.

## Limitations

- Grounding is *prompted*: the auxiliary VLM is prompted to emit boxes; it is
  not a native detection model. Accuracy is good for layout/UI/scene
  understanding but not pixel-perfect.
- Requires an OpenRouter-capable auxiliary VLM that accepts image input (check
  `input_modalities` before choosing).
- Main-model benefits are best for models with strong spatial reasoning over
  coordinate text (DeepSeek-family models were the original target).

## License

MIT © 2026 Binglun Li. Built as a Hermes Agent plugin with Nous Research's
Hermes Agent.
