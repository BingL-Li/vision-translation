#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vision-translation CLI — cross-language protocol bridge (PROTOCOL v1)
====================================================================

This is the *only* cross-language contract of the vision-translation
ecosystem. Any adapter in any language (Python, TypeScript, Rust, Go, …)
talks to the core by spawning this CLI and speaking JSON. Adapters must NOT
re-implement core logic (parsing, prompts, VLM calls) — see CONTRIBUTING.md.

---------------------------------------------------------------------------
PROTOCOL v1 (authoritative definition)
---------------------------------------------------------------------------

1. OUTPUT CONTRACT
   stdout carries EXACTLY ONE JSON object, nothing else. All human-readable
   logs go to stderr. An adapter can always do `JSON.parse(stdout)` — if
   that ever fails, it is a bug in the CLI, not in the adapter.

   Successful parse:
     {"protocol": 1,
      "core_version": "0.2.0",
      "status": "ok",
      "context": "<vision-context>…</vision-context>",
      "model": "xiaomi/mimo-v2.5"}

   Fail-closed (the protocol is alive, but the vision parse could not be
   produced — a LEGAL result, exit code 0):
     {"protocol": 1, "core_version": "0.2.0",
      "status": "unavailable",
      "unavailable": {"reason": "<reason>"}}

     reason ∈ {no_api_key, auth, rate_limited, upstream,
               vlm_invalid_output, invalid_image, internal}
       no_api_key        no OpenRouter key found (env or ~/.hermes/.env)
       auth              HTTP 401/403 — key present but rejected
       rate_limited      HTTP 429
       upstream          other HTTP / network errors from the VLM endpoint
       vlm_invalid_output  VLM returned unusable JSON 3× (fail-closed)
       invalid_image     image file unreadable / empty
       internal          anything else

   Request error (the call itself was malformed — the adapter did something
   wrong; exit code nonzero):
     {"protocol": 1, "core_version": "0.2.0",
      "status": "error",
      "error": {"code": "usage" | "image_not_found" | "internal",
                "message": "human-readable detail"}}

2. EXIT CODES
   0  → status is "ok" OR "unavailable" (both are legal results)
   1  → status is "error" (image_not_found / internal)
   2  → status is "error" with code "usage" (bad argv or bad stdin envelope)
   Adapters should branch on `status`, not on the exit code; the exit code
   exists for shell users.

3. INPUT
   Positional:   python cli.py <image_path> ["question"]
   Stdin envelope (preferred for cross-filesystem / agent use — the image
   travels with the request, so a remote adapter does not need shared
   storage). A JSON object on stdin:
     {"protocol": 1,
      "image": {"path": "/abs/or/rel/path"}          # xor
             | {"b64": "<base64>", "ext": ".png"},   # xor
      "question": "optional guiding question",
      "options": {"model": "…", "max_objects": 16}}
   argv wins over stdin when both are present. Fields are forward-compatible:
   unknown fields are ignored, missing optional fields get defaults.

4. READ-ONLY COMMANDS (no tokens, no network — safe for CI handshakes)
   python cli.py --self-check
     → {"protocol":1, "core_version":"0.2.0", "status":"ok"|"unavailable",
        "checks": {"openrouter_key": true|false, "key_source": "env"|"~/.hermes/.env"|null}}
     Exit 0 in both cases.
   python cli.py --protocol-version
     → {"protocol":1, "core_version":"0.2.0", "cli":"0.2.0"}   exit 0

5. VERSIONING
   protocol == 1 forever for this shape; a breaking change to the envelope or
   response bumps the protocol number (major bump of the whole repo). Core
   behavioural changes that keep the protocol shape only bump core_version.

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
def _load_env_key(name: str) -> str:
    """Key resolution order: process env, ~/.hermes/.env, ~/.env."""
    for p in (Path.home() / ".hermes" / ".env", Path.home() / ".env"):
        if p.is_file():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith(name + "="):
                        return line.split("=", 1)[1].strip()
            except OSError:
                pass
    return os.environ.get(name, "")


def _key_status() -> Dict[str, Any]:
    env_val = os.environ.get("OPENROUTER_API_KEY", "")
    if env_val:
        return {"present": True, "source": "env"}
    for p in (Path.home() / ".hermes" / ".env", Path.home() / ".env"):
        if p.is_file():
            try:
                if any(l.strip().startswith("OPENROUTER_API_KEY=")
                       for l in p.read_text(encoding="utf-8").splitlines()):
                    return {"present": True, "source": str(p)}
            except OSError:
                pass
    return {"present": False, "source": None}


def _ensure_key() -> None:
    """Set OPENROUTER_API_KEY into the process env if found on disk, so the
    core (which reads os.environ) works for adapters that only pass argv."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        k = _load_env_key("OPENROUTER_API_KEY")
        if k:
            os.environ["OPENROUTER_API_KEY"] = k


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
        if "OPENROUTER_API_KEY" in msg:
            return {"status": "unavailable", "reason": "no_api_key", "message": msg}
        if "HTTP 429" in msg:
            return {"status": "unavailable", "reason": "rate_limited", "message": msg}
        if "HTTP 401" in msg or "HTTP 403" in msg:
            return {"status": "unavailable", "reason": "auth", "message": msg}
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
    if img.get("b64"):
        try:
            raw = base64.b64decode(str(img["b64"]), validate=True)
        except Exception:
            return None
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
        "key_source": key["source"],
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
        image_path = _resolve_image_path(envelope)

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
    _ensure_key()
    try:
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
