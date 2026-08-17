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
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import cli  # noqa: E402

CORE_VERSION = cli.CORE_VERSION  # dynamic: version bumps never break these tests


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
    assert payload["core_version"] == CORE_VERSION
    assert payload["status"] in ("ok", "unavailable")  # key present or not
    assert "checks" in payload and "openrouter_key" in payload["checks"]


def test_protocol_version_subprocess():
    r = subprocess.run([sys.executable, "cli.py", "--protocol-version"],
                       cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    payload = json.loads(r.stdout.strip())
    assert payload["protocol"] == 1
    assert payload["status"] == "ok"
    assert payload["core_version"] == CORE_VERSION
    assert payload["cli"] == CORE_VERSION


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
    assert payload["core_version"] == CORE_VERSION


def test_unavailable_no_api_key(run_cli, fake_image, monkeypatch):
    import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_load_env_key", lambda name: "")  # no key anywhere
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("VISION_TRANSLATE_API_KEY", raising=False)
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

# --------------------------------------------------------------------------- #
# P0-4: non-UTF-8 .env must never crash the CLI; stdout stays valid JSON
# --------------------------------------------------------------------------- #
def test_self_check_non_utf8_env(run_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    env_dir = tmp_path / ".hermes"
    env_dir.mkdir()
    (env_dir / ".env").write_bytes(b"OPENROUTER_API_KEY=\xff\xfe\n")

    payload, code = run_cli("--self-check", monkeypatch=monkeypatch)
    assert code == 0
    assert payload["protocol"] == 1
    assert payload["status"] in ("ok", "unavailable")
    assert "checks" in payload


def test_translate_non_utf8_env_keeps_json_stdout(run_cli, fake_image, tmp_path, monkeypatch):
    import cli as cli_mod
    import vision_translation as vt

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    env_dir = tmp_path / ".hermes"
    env_dir.mkdir()
    (env_dir / ".env").write_bytes(b"OPENROUTER_API_KEY=\xff\xfe\n")

    def fake_call(model, messages, **kw):
        return {"choices": [{"message": {"content": json.dumps({
            "summary": "mock scene",
            "objects": [{"label": "widget", "bbox": [0, 0, 100, 100],
                         "confidence": 0.9}],
        })}}]}

    monkeypatch.setattr(vt, "_call", fake_call)
    payload, code = run_cli(fake_image, monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "ok"
    assert "<vision-context>" in payload["context"]


# --------------------------------------------------------------------------- #
# P1-1: network / upstream errors classify as unavailable/upstream, exit 0
# --------------------------------------------------------------------------- #
def test_unavailable_upstream_network_error(run_cli, fake_image, monkeypatch):
    import vision_translation as vt

    def fake_call(model, messages, **kw):
        raise RuntimeError("OpenRouter call failed: upstream network error: <urlopen error timed out>")

    monkeypatch.setattr(vt, "_call", fake_call)
    payload, code = run_cli(fake_image, monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "upstream"


def test_unavailable_upstream_non_json_response(run_cli, fake_image, monkeypatch):
    import vision_translation as vt

    def fake_call(model, messages, **kw):
        raise RuntimeError("OpenRouter call failed: upstream non-JSON response: Expecting value: line 1 column 1")

    monkeypatch.setattr(vt, "_call", fake_call)
    payload, code = run_cli(fake_image, monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "upstream"


# --------------------------------------------------------------------------- #
# P1-2: invalid/empty base64 → unavailable/invalid_image, exit 0
# --------------------------------------------------------------------------- #
def test_stdin_invalid_b64_invalid_image(run_cli, monkeypatch):
    envelope = json.dumps({"protocol": 1,
                           "image": {"b64": "!!not-base64!!", "ext": ".png"}})
    payload, code = run_cli(stdin_data=envelope, monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "invalid_image"


def test_stdin_empty_b64_invalid_image(run_cli, monkeypatch):
    envelope = json.dumps({"protocol": 1,
                           "image": {"b64": "", "ext": ".png"}})
    payload, code = run_cli(stdin_data=envelope, monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "invalid_image"


def test_stdin_missing_image_is_usage(run_cli, monkeypatch):
    envelope = json.dumps({"protocol": 1, "question": "no image field"})
    payload, code = run_cli(stdin_data=envelope, monkeypatch=monkeypatch)
    assert code == 2
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "usage"


# --------------------------------------------------------------------------- #
# P1-3: unreadable/empty files → unavailable/invalid_image, exit 0
# --------------------------------------------------------------------------- #
def test_unreadable_file_invalid_image(run_cli, tmp_path):
    img = tmp_path / "unreadable.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    img.chmod(0)

    payload, code = run_cli(str(img))
    assert code == 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "invalid_image"


def test_empty_file_invalid_image(run_cli, tmp_path):
    img = tmp_path / "empty.jpg"
    img.write_bytes(b"")

    payload, code = run_cli(str(img))
    assert code == 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "invalid_image"


# --------------------------------------------------------------------------- #
# P1-5: Hermes bridge failure path returns plain text (no <vision-context>)
# --------------------------------------------------------------------------- #
def _load_plugin_module(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "vision_translation_plugin", REPO_ROOT / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_handler_failure_is_plain_text(monkeypatch, tmp_path):
    mod = _load_plugin_module(monkeypatch)
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)

    def fake_analyze(path, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod.vt, "analyze", fake_analyze)
    out = mod._handler({"image_path": str(img)})
    assert "<vision-context" not in out
    assert "vision unavailable" in out
    assert "boom" in out


def test_handler_success_still_returns_vision_context(monkeypatch, tmp_path):
    mod = _load_plugin_module(monkeypatch)
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)

    def fake_analyze(path, **kw):
        return "<vision-context>\nok\n</vision-context>"

    monkeypatch.setattr(mod.vt, "analyze", fake_analyze)
    out = mod._handler({"image_path": str(img)})
    assert "<vision-context>" in out


# --------------------------------------------------------------------------- #
# P1-6: _load_env_key must be process-env-first
# --------------------------------------------------------------------------- #
def test_load_env_key_env_priority(monkeypatch, tmp_path):
    import cli as cli_mod

    monkeypatch.setenv("HOME", str(tmp_path))
    env_dir = tmp_path / ".hermes"
    env_dir.mkdir()
    env_file = env_dir / ".env"
    env_file.write_text("OPENROUTER_API_KEY=file-value\n")

    monkeypatch.setenv("OPENROUTER_API_KEY", "env-value")
    assert cli_mod._load_env_key("OPENROUTER_API_KEY") == "env-value"

    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert cli_mod._load_env_key("OPENROUTER_API_KEY") == "file-value"

    env_file.unlink()
    assert cli_mod._load_env_key("OPENROUTER_API_KEY") is None


# --------------------------------------------------------------------------- #
# VLM endpoint config: --self-check key_source + .env passthrough
# --------------------------------------------------------------------------- #
def test_self_check_vision_translate_key(run_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VISION_TRANSLATE_API_KEY", "sk-vt")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    payload, code = run_cli("--self-check", monkeypatch=monkeypatch)
    assert code == 0
    assert payload["protocol"] == 1
    assert payload["status"] == "ok"
    assert payload["checks"]["openrouter_key"] is True
    assert payload["checks"]["key_source"] == "vision_translate"


def test_self_check_openrouter_key(run_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
    monkeypatch.delenv("VISION_TRANSLATE_API_KEY", raising=False)

    payload, code = run_cli("--self-check", monkeypatch=monkeypatch)
    assert code == 0
    assert payload["protocol"] == 1
    assert payload["status"] == "ok"
    assert payload["checks"]["openrouter_key"] is True
    assert payload["checks"]["key_source"] == "openrouter"


def test_self_check_new_key_wins_when_both_set(run_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VISION_TRANSLATE_API_KEY", "sk-new")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-old")

    payload, code = run_cli("--self-check", monkeypatch=monkeypatch)
    assert code == 0
    assert payload["protocol"] == 1
    assert payload["status"] == "ok"
    assert payload["checks"]["openrouter_key"] is True
    assert payload["checks"]["key_source"] == "vision_translate"


def test_ensure_key_passes_new_key_and_base_url_from_dotenv(monkeypatch, tmp_path):
    import cli as cli_mod

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("VISION_TRANSLATE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("VISION_TRANSLATE_BASE_URL", raising=False)

    env_dir = tmp_path / ".hermes"
    env_dir.mkdir()
    (env_dir / ".env").write_text(
        "VISION_TRANSLATE_API_KEY=sk-dotenv\n"
        "VISION_TRANSLATE_BASE_URL=https://example.com/v1/chat/completions\n"
    )

    cli_mod._ensure_key()
    assert os.environ["VISION_TRANSLATE_API_KEY"] == "sk-dotenv"
    assert os.environ["VISION_TRANSLATE_BASE_URL"] == "https://example.com/v1/chat/completions"


def test_classify_missing_key_covers_both_names():
    import cli as cli_mod

    assert cli_mod._classify(
        RuntimeError("VISION_TRANSLATE_API_KEY or OPENROUTER_API_KEY environment variable is not set")
    )["reason"] == "no_api_key"
    assert cli_mod._classify(
        RuntimeError("OPENROUTER_API_KEY environment variable is not set")
    )["reason"] == "no_api_key"


def test_unavailable_no_api_key_both_names_absent(run_cli, fake_image, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("VISION_TRANSLATE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    payload, code = run_cli(fake_image, monkeypatch=monkeypatch)
    assert code == 0
    assert payload["status"] == "unavailable"
    assert payload["unavailable"]["reason"] == "no_api_key"
