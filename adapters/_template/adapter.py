#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal adapter scaffold — PROTOCOL v1 consumer.

Shows the canonical adapter pattern in the fewest lines:
  1. spawn the core CLI (cross-language boundary)
  2. JSON.parse(stdout) — never anything else
  3. branch on `status`: ok → use context; unavailable → fall back /
     surface reason; error → report the bug

This is intentionally tiny. The template README states the one rule:
adapters never re-implement core logic.
"""
import json
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLI = REPO_ROOT / "cli.py"


class VisionResult:
    def __init__(self, ok: bool, context: str = "", reason: str = "",
                 error: str = ""):
        self.ok = ok              # True when status == "ok"
        self.context = context    # <vision-context> text (status ok)
        self.reason = reason      # unavailable reason, e.g. "rate_limited"
        self.error = error        # error message (status error)

    def __repr__(self):
        return (f"VisionResult(ok={self.ok}, reason={self.reason!r}, "
                f"error={self.error!r}, context_len={len(self.context)})")


def translate(image_path: str, question: str = "",
              model: str = "") -> VisionResult:
    """Run the CLI, speak the protocol, return a clean result object."""
    cmd = [sys.executable, str(CLI), str(image_path)]
    if question:
        cmd += [question]
    env_extra = {}
    if model:
        env_extra["VISION_TRANSLATE_VLM"] = model

    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120,
        env={**__import__("os").environ, **env_extra},
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        # stdout purity violation = a bug in the CLI, not the adapter
        return VisionResult(False, error=f"protocol violation: stdout not JSON: {e}")

    if payload.get("status") == "ok":
        return VisionResult(True, context=payload.get("context", ""))
    if payload.get("status") == "unavailable":
        return VisionResult(False, reason=payload.get("unavailable", {}).get("reason", ""))
    err = payload.get("error", {})
    return VisionResult(False, error=f"{err.get('code')}: {err.get('message')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <image_path> [question]", file=sys.stderr)
        sys.exit(2)
    q = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
    r = translate(sys.argv[1], q)
    if r.ok:
        print(r.context)
    else:
        print(f"vision unavailable ({r.reason or r.error})", file=sys.stderr)
        sys.exit(1)
