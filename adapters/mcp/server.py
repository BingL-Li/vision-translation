"""MCP adapter for vision-translation — the universal bridge for any MCP host.

Exposes the core's <vision-context> as a single MCP tool, ``vision_translate``,
so any MCP-capable agent (dsh, Claude Code, Cursor, Hermes, ...) can ground
images without knowing anything about Python or the core.

Design rules (see PROTOCOL.md / CONTRIBUTING.md):
- Never re-implement core logic. This server imports the core directly and
  reuses the CLI's status classification (``cli._classify``) as the single
  source of truth for the ok / unavailable / error mapping.
- ``unavailable`` is a legal, fail-closed result: it returns a normal tool
  result with an explicit "do not guess" message. Only ``error`` surfaces as
  an MCP error (isError), so hosts treat it as a broken call worth retrying.
- stdout belongs to JSON-RPC: nothing in this process may print to stdout;
  any logging must go to stderr.

Run:  python server.py          (needs: pip install mcp)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import vision_translation as vt  # noqa: E402
from cli import _classify, _ensure_key  # noqa: E402

mcp = FastMCP("vision-translation")


@mcp.tool()
def vision_translate(image: str, question: str = "", model: str = "",
                     max_objects: int = 0) -> str:
    """Analyze an image and return a structured <vision-context> grounding
    block: visual primitives with normalized bounding boxes, spatial
    relations (left_of / above / inside / overlaps), and visible text.

    Use this when answering needs to know what is in an image and where.
    Pass ``image`` as a local file path.

    If the result says vision is unavailable, do NOT guess or fabricate
    image content — tell the user you cannot see the image.
    """
    _ensure_key()
    try:
        ctx = vt.analyze(
            image,
            question=question,
            model=model or os.environ.get("VISION_TRANSLATE_VLM") or vt.DEFAULT_VLM_MODEL,
            max_objects=max(1, min(max_objects or vt.MAX_PRIMITIVES, vt.MAX_PRIMITIVES)),
        )
    except Exception as exc:  # noqa: BLE001 — protocol boundary: classify, never crash
        cls = _classify(exc)
        if cls["status"] == "unavailable":
            return (
                f"vision unavailable (reason: {cls['reason']}): {cls['message']}\n"
                "Do not guess or fabricate the image content."
            )
        raise RuntimeError(f"{cls['code']}: {cls['message']}") from exc
    return ctx


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
