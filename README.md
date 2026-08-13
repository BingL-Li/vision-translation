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
