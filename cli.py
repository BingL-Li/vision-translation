#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vision-translation CLI — cross-language protocol bridge (PROTOCOL v1).

The only cross-language contract of the vision-translation ecosystem: any
adapter (Python, TypeScript, Rust, …) spawns this CLI and speaks JSON to
reach the core. Adapters must NOT re-implement core logic (parsing, prompts,
VLM calls) — see CONTRIBUTING.md.

Contract in brief (the normative spec lives in PROTOCOL.md):

  stdout  = exactly ONE JSON object, nothing else (logs -> stderr)
  status  = "ok" | "unavailable" (fail-closed, exit 0) | "error" (exit 1/2)
  input   = argv <image_path> ["question"]  OR  stdin JSON envelope
            {"protocol": 1, "image": {"path"|"b64", ...},
             "question": "...", "options": {...}}
  handshake commands (no tokens, no network):
            --self-check | --protocol-version
  versioning: protocol field bumps on breaking shape changes; core_version
            on compatible behaviour changes.

CORE_VERSION must stay in sync with `version:` in plugin.yaml (CI asserts it).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import vision_translation as vt  # the one and only core; import-pure

PROTOCOL_VERSION = 1
CORE_VERSION = "0.2.0"  # keep in sync with plugin.yaml
CLI_VERSION = "0.2.0"

_USAGE = (
    f"usage: {sys.argv[0]} <image_path> [\"question\"]\n"
    f"       {sys.argv[0]} --self-check | --protocol-version\n"
    f"       {sys.argv[0]} < stdin-json-envelope   (see module docstring, PROTOCOL v1)"
)


# --------------------------------------------------------------------------- #
# env / key handling (adapter-layer concern — the core never touches this)
# --------------------------------------------------------------------------- #
def _load_env_key(name: str) -> Optional[str]:
    """Key resolution order: process env, ~/.hermes/.env, ~/.env."""
    env_val = os.environ.get(name)
    if env_val is not None:
        return env_val
    for p in (Path.home() / ".hermes" / ".env", Path.home() / ".env"):
        if p.is_file():
            try:
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line.startswith(name + "="):
                        return line.split("=", 1)[1].strip()
            except (OSError, UnicodeDecodeError):
                pass
    return None


def _key_source(name: str) -> Optional[str]:
    """Where a key/value comes from: process env, or one of the .env files."""
    if os.environ.get(name):
        return "env"
    for p in (Path.home() / ".hermes" / ".env", Path.home() / ".env"):
        if p.is_file():
            try:
                if any(l.strip().startswith(name + "=")
                       for l in p.read_text(encoding="utf-8", errors="replace").splitlines()):
                    return str(p)
            except (OSError, UnicodeDecodeError):
                pass
    return None


def _key_status() -> Dict[str, Any]:
    """Check both VLM key names; the new name wins when both are present."""
    for label, name in (("vision_translate", "VISION_TRANSLATE_API_KEY"),
                        ("openrouter", "OPENROUTER_API_KEY")):
        source = _key_source(name)
        if source:
            return {"present": True, "source": source, "key_source": label}
    return {"present": False, "source": None, "key_source": "none"}


def _ensure_key() -> None:
    """Expose .env-configured VLM keys/base URL to the core's process env.

    New key name wins when both are configured; the legacy OpenRouter key is
    still written so the core fallback keeps working for adapters that only
    pass argv and have no process environment of their own.
    """
    if not os.environ.get("VISION_TRANSLATE_API_KEY"):
        k = _load_env_key("VISION_TRANSLATE_API_KEY")
        if k:
            os.environ["VISION_TRANSLATE_API_KEY"] = k
    if not os.environ.get("OPENROUTER_API_KEY"):
        k = _load_env_key("OPENROUTER_API_KEY")
        if k:
            os.environ["OPENROUTER_API_KEY"] = k
    if not os.environ.get("VISION_TRANSLATE_BASE_URL"):
        v = _load_env_key("VISION_TRANSLATE_BASE_URL")
        if v:
            os.environ["VISION_TRANSLATE_BASE_URL"] = v
    if not os.environ.get("VISION_TRANSLATE_VLM"):
        v = _load_env_key("VISION_TRANSLATE_VLM")
        if v:
            os.environ["VISION_TRANSLATE_VLM"] = v


# --------------------------------------------------------------------------- #
# error classification (status, reason-or-code)
# --------------------------------------------------------------------------- #
def _classify(err: Exception) -> Dict[str, Any]:
    msg = str(err)
    if isinstance(err, FileNotFoundError):
        return {"status": "error", "code": "image_not_found", "message": msg}
    if isinstance(err, ValueError):  # empty image, bad base64, …
        return {"status": "unavailable", "reason": "invalid_image", "message": msg}
    if isinstance(err, RuntimeError):
        if "VISION_TRANSLATE_API_KEY" in msg or "OPENROUTER_API_KEY" in msg:
            return {"status": "unavailable", "reason": "no_api_key", "message": msg}
        if "HTTP 429" in msg:
            return {"status": "unavailable", "reason": "rate_limited", "message": msg}
        if "HTTP 401" in msg or "HTTP 403" in msg:
            return {"status": "unavailable", "reason": "auth", "message": msg}
        if "upstream network error" in msg or "upstream non-JSON response" in msg:
            return {"status": "unavailable", "reason": "upstream", "message": msg}
        if "HTTP" in msg:
            return {"status": "unavailable", "reason": "upstream", "message": msg}
        if "invalid JSON" in msg:
            return {"status": "unavailable", "reason": "vlm_invalid_output", "message": msg}
    return {"status": "error", "code": "internal", "message": msg}


# --------------------------------------------------------------------------- #
# envelope handling
# --------------------------------------------------------------------------- #
def _is_tty(stream: Any) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _read_envelope(argv: List[str]) -> Optional[Dict[str, Any]]:
    """Parse the stdin JSON envelope; None when stdin carried no usable JSON."""
    if not argv and not _is_tty(sys.stdin):
        raw = sys.stdin.read()
        if raw.strip():
            try:
                env = json.loads(raw)
                if isinstance(env, dict) and env.get("protocol") == PROTOCOL_VERSION:
                    return env
            except json.JSONDecodeError:
                pass
    return None


def _resolve_image_path(envelope: Optional[Dict[str, Any]]) -> Optional[Path]:
    """argv path first, then stdin envelope path/b64. Returns None when the
    envelope is present but has no usable image (caller reports usage)."""
    img = (envelope or {}).get("image") or {}
    if not isinstance(img, dict):
        return None
    if img.get("path"):
        return Path(str(img["path"])).expanduser()
    if img.get("b64") is not None:
        try:
            raw = base64.b64decode(str(img["b64"]), validate=True)
        except Exception as e:
            raise ValueError(f"invalid base64 image data: {e}") from e
        if not raw:
            raise ValueError("invalid base64 image data: empty payload")
        suffix = str(img.get("ext") or ".jpg")
        fd, tmp = tempfile.mkstemp(prefix="vt-", suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        return Path(tmp)
    return None


# --------------------------------------------------------------------------- #
# response builders
# --------------------------------------------------------------------------- #
def _base() -> Dict[str, Any]:
    return {"protocol": PROTOCOL_VERSION, "core_version": CORE_VERSION}


def _emit(payload: Dict[str, Any], exit_code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def _cmd_self_check() -> int:
    key = _key_status()
    payload = _base()
    if key["present"]:
        payload["status"] = "ok"
    else:
        payload["status"] = "unavailable"
        payload["unavailable"] = {"reason": "no_api_key"}
    payload["checks"] = {
        "openrouter_key": key["present"],
        "key_source": key["key_source"],
        "key_origin": key["source"],
        "core_import": "ok",
    }
    return _emit(payload, 0)


def _cmd_protocol_version() -> int:
    return _emit({**_base(), "status": "ok", "cli": CLI_VERSION}, 0)


def _cmd_translate(argv: List[str], envelope: Optional[Dict[str, Any]]) -> int:
    # --- inputs ----------------------------------------------------------- #
    image_path: Optional[Path] = None
    question = ""
    options: Dict[str, Any] = {}

    if argv:
        image_path = Path(argv[0]).expanduser()
        question = " ".join(argv[1:])
    else:
        if envelope is None:
            return _emit({**_base(), "status": "error",
                          "error": {"code": "usage", "message": _USAGE}}, 2)
        question = str(envelope.get("question") or "")
        options = envelope.get("options") or {}
        if not isinstance(options, dict):
            options = {}
        try:
            image_path = _resolve_image_path(envelope)
        except Exception as e:  # noqa: BLE001 — protocol boundary: classify, never crash
            cls = _classify(e)
            if cls["status"] == "unavailable":
                return _emit({**_base(), "status": "unavailable",
                              "unavailable": {"reason": cls["reason"]}}, 0)
            return _emit({**_base(), "status": "error",
                          "error": {"code": cls["code"], "message": cls["message"]}}, 1)

    if image_path is None:
        return _emit({**_base(), "status": "error",
                      "error": {"code": "usage",
                                "message": "no image in argv or stdin envelope"}}, 2)

    # --- model / options (adapter layer; core defaults stay authoritative) #
    model = str(options.get("model") or os.environ.get("VISION_TRANSLATE_VLM")
                or vt.DEFAULT_VLM_MODEL)
    try:
        max_objects = int(options.get("max_objects") or vt.MAX_PRIMITIVES)
    except (TypeError, ValueError):
        max_objects = vt.MAX_PRIMITIVES
    max_objects = max(1, min(max_objects, vt.MAX_PRIMITIVES))

    # --- run core (the only intelligence; we never re-implement it) ------- #
    try:
        _ensure_key()
        ctx = vt.analyze(str(image_path), question=question,
                         model=model, max_objects=max_objects)
    except Exception as e:  # noqa: BLE001 — protocol boundary: classify, never crash
        cls = _classify(e)
        if cls["status"] == "unavailable":
            payload = {**_base(), "status": "unavailable",
                       "unavailable": {"reason": cls["reason"]}}
            return _emit(payload, 0)
        payload = {**_base(), "status": "error",
                   "error": {"code": cls["code"], "message": cls["message"]}}
        return _emit(payload, 1)

    return _emit({**_base(), "status": "ok",
                  "context": ctx, "model": model}, 0)


# --------------------------------------------------------------------------- #
# entry point (import-safe: no side effects at import)
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == "--self-check":
        return _cmd_self_check()
    if argv and argv[0] == "--protocol-version":
        return _cmd_protocol_version()
    if argv and argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0

    envelope = _read_envelope(argv)
    return _cmd_translate(argv, envelope)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
