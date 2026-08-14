"""vision-translation plugin — Translation with Visual Primitives.

Registers one tool: ``vision_translate``.

Naming: a deliberate counterpoint to DeepSeek's paper *Thinking with Visual
Primitives* — that paper makes a model think *in* visual primitives; this
plugin works the other way: an external layer translates vision into
primitives and injects them as text, leaving the main model (e.g. DeepSeek)
untouched. External, generic, model-agnostic.

Responsibility boundary (inspired by the OpenHanako Vision Bridge):
  image -> auxiliary VLM structured JSON -> canonical primitives (norm-1000 xyxy)
       -> programmatic spatial relations -> <vision-context> text
  The tool returns ONLY <vision-context>; it never calls a text LLM —
  the current Hermes main model reasons over the context directly.

Difference vs the built-in vision_analyze:
  - built-in: one-line image description (cheap)
  - this tool: bbox coordinates / spatial relations / structured entities /
    OCR, e.g. "who is to the left of whom", "how many X", UI element
    locations, schematic component bboxes.
"""
from __future__ import annotations

import os
from pathlib import Path

# Dual-mode import: when Hermes loads this plugin as a package, the relative
# import is used; when pytest or any tool imports this file as a bare top-level
# module (repo root dir name contains a hyphen, so it can never be a real Python
# package), we fall back to the absolute import (repo root is on sys.path via
# pyproject.toml pythonpath).
try:
    from . import vision_translation as vt
except ImportError:  # pragma: no cover - bare top-level import (pytest)
    import vision_translation as vt  # type: ignore[no-redef]

TOOL_NAME = "vision_translate"
TOOLSET = "vision_translation"
EMOJI = "🧭"
_MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25MB guard


_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Translation with Visual Primitives: translate an image into a "
        "structured visual-primitives context (object bbox coordinates / "
        "spatial relations / OCR / scene summary) and return <vision-context> "
        "text. Use this tool when you need coordinates, positions, counting, "
        "UI or schematic component locations, or structured entities; use the "
        "built-in vision_analyze (cheaper) for a one-line image description. "
        "The image is sent to an OpenRouter auxiliary vision model."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Local image path (required). expanduser is applied.",
            },
            "question": {
                "type": "string",
                "description": "Optional question to guide parsing focus.",
            },
            "max_objects": {
                "type": "integer",
                "description": "Max primitives to keep (optional, default 12).",
            },
        },
        "required": ["image_path"],
    },
}


def _handler(args: dict, **kw) -> str:
    """Synchronous handler. Returns an error text on failure instead of
    raising (keeps the turn alive), preserving fail-closed semantics."""
    image_path = str(args.get("image_path") or "").strip()
    question = str(args.get("question") or "").strip()
    try:
        max_objects = int(args.get("max_objects") or 12)
    except (TypeError, ValueError):
        max_objects = 12
    max_objects = max(1, min(max_objects, vt.MAX_PRIMITIVES))

    if not image_path:
        return '{"success": false, "error": "missing image_path"}'
    p = Path(image_path).expanduser()
    if not p.is_file():
        return f'{{"success": false, "error": "image not found: {p}"}}'
    try:
        if p.stat().st_size > _MAX_IMAGE_BYTES:
            return f'{{"success": false, "error": "image too large (>{_MAX_IMAGE_BYTES // (1024 * 1024)}MB)"}}'
    except OSError as e:
        return f'{{"success": false, "error": "cannot access image: {e}"}}'

    # Model: env override first, else the verified default (never hardcode
    # anything beyond the user's configuration).
    model = os.environ.get("VISION_TRANSLATE_VLM", vt.DEFAULT_VLM_MODEL)

    try:
        ctx = vt.analyze(str(p), question=question, model=model, max_objects=max_objects)
    except Exception as e:
        # fail-closed: do not inject empty/fabricated context; hand the error
        # to the agent so it can decide whether to fall back to vision_analyze.
        return (
            "<vision-context>\n"
            f'{{"status": "unavailable", "error": "vision parse failed: {e}"}}\n'
            "</vision-context>"
        )

    # Return only <vision-context>, no redundant copy; annotate the source
    # model so the agent can judge reliability.
    return (
        f"<vision-source model=\"{model}\" coord=\"{vt.COORD}\" box_order=\"{vt.BOX_ORDER}\" "
        f"grounding=\"{vt.GROUNDING}\"/>\n{ctx}"
    )


def _check_available() -> bool:
    """Availability gate: needs an OpenRouter key to work."""
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def register(ctx) -> None:
    ctx.register_tool(
        name=TOOL_NAME,
        toolset=TOOLSET,
        schema=_SCHEMA,
        handler=_handler,
        check_fn=_check_available,
        requires_env=["OPENROUTER_API_KEY"],
        is_async=False,
        description=_SCHEMA["description"],
        emoji=EMOJI,
    )
