"""CLI protocol tests — offline, no network, no paid requests.

The protocol contract is: stdout carries exactly one JSON object (never
logs), `unavailable` is a legal result with exit 0 (fail-closed ≠ crash),
`error` is a malformed request with a nonzero exit, and every response
carries protocol + core_version.

Two layers:
  1. in-process: import cli, monkeypatch the VLM at the core HTTP boundary
     (vt._call) — exercises status classification, reason mapping, exit codes.
  2. subprocess: real `python cli.py` for the read-only commands and the
     no-image usage error — verifies stdout purity (single JSON line,
     nothing else) exactly as a TS/Rust/Go adapter would consume it.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def fake_image(tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    return str(img)


@pytest.fixture
def run_cli():
    """In-process runner: returns (payload, exit_code)."""
    def _run(*argv, stdin_data=None, monkeypatch=None):
        import io
        import cli as cli_mod

        old_stdin, old_stdout = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(stdin_data or "")
        sys.stdout = io.StringIO()
        try:
            code = cli_mod.main(list(argv))
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_stdin, old_stdout
        return json.loads(out), code
    return _run


# --------------------------------------------------------------------------- #
# read-only commands (no key, no network)
# --------------------------------------------------------------------------- #
def test_self_check_stdout_purity():
    """Real subprocess: stdout is a single JSON line, stderr stays empty."""
    r = subprocess.run([sys.executable, "cli.py", "--self-check"],
                       cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    assert r.stderr.strip() == ""  # logs must never pollute stdout
    payload = json.loads(r.stdout.strip())
    assert payload["protocol"] == 1
    assert payload["core_version"] == "0.2.0"
    assert payload["status"] in ("ok", "unavailable")  # key present or not
    assert "checks" in payload and "openrouter_key" in payload["checks"]


def test_protocol_version_subprocess():
    r = subprocess.run([sys.executable, "cli.py", "--protocol-version"],
                       cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    payload = json.loads(r.stdout.strip())
    assert payload["protocol"] == 1
    assert payload["status"] == "ok"
    assert payload["core_version"] == "0.2.0"
    assert payload["cli"] == "0.2.0"


def test_usage_error_no_input(run_cli):
    """No argv + no stdin envelope → error/usage, exit 2, still valid JSON."""
    payload, code = run_cli()
    assert code == 2
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "usage"
    assert payload["protocol"] == 1


def test_image_not_found(run_cli):
    payload, code = run_cli("/nonexistent/definitely-missing.jpg")
    assert code == 1
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "image_not_found"


# --------------------------------------------------------------------------- #
# translate path — VLM mocked at the core HTTP boundary
# --------------------------------------------------------------------------- #
def test_ok_payload(run_cli, fake_image, monkeypatch):
    import cli as cli_mod
    import vision_translation as vt

    def fake_call(model, messages, **kw):
        return {"choices": [{"message": {"content": json.dumps({
            "summary": "mock scene", "scene": "mock",
            "objects": [{"label": "widget", "bbox": [0, 0, 100, 100],
                         "confidence": 0.9}],
        })}}]}

    monkeypatch.setattr(vt, "_call", fake_call)
    payload, code = run_cli(fake_image, "what is this?", monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "ok"
    assert "<vision-context>" in payload["context"]
    assert payload["model"]  # echoes the model actually used
    assert payload["core_version"] == "0.2.0"


def test_unavailable_no_api_key(run_cli, fake_image, monkeypatch):
    import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_load_env_key", lambda name: "")  # no key anywhere
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    payload, code = run_cli(fake_image, monkeypatch=monkeypatch)
    assert code == 0  # fail-closed is a LEGAL result: exit 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "no_api_key"


def test_unavailable_vlm_invalid_output(run_cli, fake_image, monkeypatch):
    import vision_translation as vt

    def fake_call(model, messages, **kw):
        return {"choices": [{"message": {"content": "garbage not json"}}]}

    monkeypatch.setattr(vt, "_call", fake_call)
    payload, code = run_cli(fake_image, monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "vlm_invalid_output"


def test_unavailable_rate_limited(run_cli, fake_image, monkeypatch):
    import vision_translation as vt

    def fake_call(model, messages, **kw):
        raise RuntimeError("OpenRouter HTTP 429: too many requests")

    monkeypatch.setattr(vt, "_call", fake_call)
    payload, code = run_cli(fake_image, monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "rate_limited"


def test_unavailable_auth(run_cli, fake_image, monkeypatch):
    import vision_translation as vt

    def fake_call(model, messages, **kw):
        raise RuntimeError("OpenRouter HTTP 401: bad key")

    monkeypatch.setattr(vt, "_call", fake_call)
    payload, code = run_cli(fake_image, monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "auth"


def test_stdin_envelope_b64(run_cli, fake_image, monkeypatch):
    import base64
    import vision_translation as vt

    def fake_call(model, messages, **kw):
        return {"choices": [{"message": {"content": json.dumps({
            "summary": "b64 scene",
            "objects": [{"label": "box", "bbox": [0, 0, 50, 50],
                         "confidence": 1.0}],
        })}}]}

    monkeypatch.setattr(vt, "_call", fake_call)
    b64 = base64.b64encode(Path(fake_image).read_bytes()).decode()
    envelope = json.dumps({"protocol": 1,
                           "image": {"b64": b64, "ext": ".jpg"},
                           "question": "via stdin"})
    payload, code = run_cli(stdin_data=envelope, monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "ok"
    assert "<vision-context>" in payload["context"]


def test_bad_stdin_envelope_usage(run_cli, monkeypatch):
    payload, code = run_cli(stdin_data="this is not json", monkeypatch=monkeypatch)
    assert code == 2
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "usage"
