#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Translation with Visual Primitives — CLI demo
=============================================
Reuses the plugin core `vision_translation` (same code, no duplication):
  image -> VLM structured primitives -> spatial relations -> <vision-context>
       -> text-only LLM reasoning (demo-only step; the plugin tool itself
          does not call a text LLM)

Usage:
  python demos/vision_translate_demo.py <image_path> ["question"]

Key: OPENROUTER_API_KEY from environment or ~/.hermes/.env / ~/.env.
     Aux VLM defaults to xiaomi/mimo-v2.5; override with VISION_TRANSLATE_VLM.
     Text model defaults to deepseek; override with VISION_TRANSLATE_TEXT.
"""
import os
import sys

# Make the plugin core importable regardless of cwd (repo-relative, not user-absolute)
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

import vision_translation as vt  # noqa: E402

TEXT_MODEL = os.environ.get("VISION_TRANSLATE_TEXT", "deepseek/deepseek-v4-flash-0731")


def _load_env_key(name: str) -> str:
    for p in (os.path.expanduser("~/.hermes/.env"), os.path.expanduser("~/.env")):
        if os.path.isfile(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get(name, "")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(f"usage: {sys.argv[0]} <image_path> [\"question\"]", file=sys.stderr)
        return 2
    image_path = args[0]
    question = " ".join(args[1:]) if len(args) > 1 else "识别这张图片"

    api_key = _load_env_key("OPENROUTER_API_KEY")
    if not api_key:
        print("missing OPENROUTER_API_KEY (env or ~/.hermes/.env)", file=sys.stderr)
        return 2
    os.environ.setdefault("OPENROUTER_API_KEY", api_key)

    vlm_model = os.environ.get("VISION_TRANSLATE_VLM", vt.DEFAULT_VLM_MODEL)
    print(f"🧭 Translation with Visual Primitives | VLM={vlm_model} | TEXT={TEXT_MODEL}")
    print(f"🖼️  {os.path.abspath(image_path)}\n❓ {question}\n" + "-" * 60)

    # 1) Plugin core: image -> <vision-context> (retries + fail-closed)
    ctx = vt.analyze(image_path, question=question, model=vlm_model)
    print("【<vision-context>】\n" + ctx + "\n" + "-" * 60)

    # 2) Demo-only step: feed the text context to a text-only LLM
    messages = [
        {"role": "system", "content": (
            "You are an assistant that can only see the textual vision context below, "
            "not the original image. Answer the user's question based on it; do not "
            "guess beyond what the context states."
        )},
        {"role": "user", "content": f"{ctx}\n\nUser question: {question}"},
    ]
    resp = vt.complete_text(TEXT_MODEL, messages)
    print(f"【LLM answer】\n{vt.extract_text(resp)}")
    usage = resp.get("usage", {})
    print(f"\n(usage in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"run failed: {e}", file=sys.stderr)
        sys.exit(1)
