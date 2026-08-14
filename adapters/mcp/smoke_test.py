"""Offline smoke test for the MCP adapter — no network, no paid calls.

Checks the three protocol states as the MCP layer maps them:
  1. ok          — mocked VLM at the core HTTP boundary → <vision-context>
  2. unavailable — no API key → normal result, explicit "do not guess"
  3. error       — missing image → MCP error (exception = isError path)

Run:  python smoke_test.py    (needs: pip install mcp)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cli  # noqa: E402
import server  # noqa: E402
import vision_translation as vt  # noqa: E402

_REAL_CALL = vt._call  # captured before any test mocks it


def _fake_image() -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    with os.fdopen(fd, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    return path


def _fake_vlm_ok() -> None:
    vt._call = lambda model, messages, **kw: {
        "choices": [{"message": {"content": json.dumps({
            "summary": "smoke scene", "scene": "smoke",
            "objects": [{"label": "widget", "bbox": [0, 0, 100, 100],
                         "confidence": 0.9}],
        })}}]
    }


def test_ok() -> None:
    _fake_vlm_ok()
    os.environ["OPENROUTER_API_KEY"] = "sk-test"
    out = server.vision_translate(_fake_image(), "what is this?")
    assert "<vision-context>" in out, out
    print("ok          ✓  returns <vision-context>")


def test_unavailable_no_key() -> None:
    vt._call = _REAL_CALL  # restore real call: it raises on missing key
    os.environ.pop("OPENROUTER_API_KEY", None)
    cli._load_env_key = lambda name: ""  # block the disk fallback
    out = server.vision_translate(_fake_image())
    assert "vision unavailable" in out and "no_api_key" in out, out
    print("unavailable ✓  fail-closed normal result, reason=no_api_key")


def test_error_missing_image() -> None:
    os.environ["OPENROUTER_API_KEY"] = "sk-test"
    try:
        server.vision_translate("/nonexistent/missing.jpg")
    except RuntimeError as exc:
        assert "image_not_found" in str(exc), exc
        print("error       ✓  raises MCP error (isError path), code=image_not_found")
    else:
        raise AssertionError("expected RuntimeError for missing image")


if __name__ == "__main__":
    test_ok()
    test_unavailable_no_key()
    test_error_missing_image()
    print("\nall smoke checks passed")
