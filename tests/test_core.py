"""Core unit tests — offline, no network, no keys.

Covers the pure-function core (`vision_translation.py`): tolerant parsing,
bbox normalization, primitives building, spatial relations, context
rendering, and the fail-closed analyze path (VLM mocked at the HTTP
boundary `_call`).
"""
import json

import pytest

import vision_translation as vt


# --------------------------------------------------------------------------- #
# parse_json_tolerant
# --------------------------------------------------------------------------- #
def test_parse_json_tolerant_fenced():
    assert vt.parse_json_tolerant('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_tolerant_embedded():
    assert vt.parse_json_tolerant('prefix {"x": [1, 2]} suffix') == {"x": [1, 2]}


def test_parse_json_tolerant_garbage():
    assert vt.parse_json_tolerant("not json at all") == {}


# --------------------------------------------------------------------------- #
# normalize_bbox
# --------------------------------------------------------------------------- #
def test_normalize_bbox_valid():
    assert vt.normalize_bbox({"bbox": [10, 20, 300, 400]}) == [10, 20, 300, 400]


def test_normalize_bbox_reversed_corners():
    assert vt.normalize_bbox({"bbox": [300, 400, 10, 20]}) == [10, 20, 300, 400]


def test_normalize_bbox_clamps_out_of_contract():
    w: list = []
    out = vt.normalize_bbox({"bbox": [-5, 0, 1500, 1000]}, warnings=w)
    assert out == [0, 0, 1000, 1000]
    assert w, "out-of-contract boxes must emit a warning"


def test_normalize_bbox_zero_area_dropped():
    assert vt.normalize_bbox({"bbox": [10, 10, 10, 400]}) is None


def test_normalize_bbox_nonfinite_dropped():
    assert vt.normalize_bbox({"bbox": [0, 0, float("inf"), 10]}) is None


# --------------------------------------------------------------------------- #
# build_primitives
# --------------------------------------------------------------------------- #
def test_build_primitives_sorts_and_caps():
    vlm = {"objects": [
        {"label": "low", "bbox": [0, 0, 100, 100], "confidence": 0.3},
        {"label": "high", "bbox": [0, 0, 200, 200], "confidence": 0.9},
    ]}
    prims = vt.build_primitives(vlm, max_objects=1)
    assert len(prims) == 1
    assert prims[0]["label"] == "high"


def test_build_primitives_accepts_alias_keys():
    vlm = {"visual_primitives": [{"name": "cat", "xyxy": [0, 0, 50, 50]}]}
    prims = vt.build_primitives(vlm)
    assert prims and prims[0]["label"] == "cat"


# --------------------------------------------------------------------------- #
# derive_spatial_relations
# --------------------------------------------------------------------------- #
def test_relations_left_of_and_above():
    prims = [
        {"id": "v1", "box": [0, 0, 100, 100]},
        {"id": "v2", "box": [500, 500, 600, 600]},
    ]
    rels = vt.derive_spatial_relations(prims)
    preds = {(r["subject"], r["predicate"], r["object"]) for r in rels}
    assert ("v1", "left_of", "v2") in preds
    assert ("v1", "above", "v2") in preds


def test_relations_inside():
    prims = [
        {"id": "v1", "box": [100, 100, 900, 900]},
        {"id": "v2", "box": [300, 300, 500, 500]},
    ]
    rels = vt.derive_spatial_relations(prims)
    assert any(r["predicate"] == "inside" for r in rels)


def test_relations_no_duplicate_overlaps():
    # IoU([0,0,500,500],[200,200,600,600]) = 90000/320000 ≈ 0.28 → overlaps fires;
    # v1-v2 and v2-v1 must dedupe to a single relation.
    prims = [
        {"id": "v1", "box": [0, 0, 500, 500]},
        {"id": "v2", "box": [200, 200, 600, 600]},
    ]
    rels = vt.derive_spatial_relations(prims)
    overlaps = [r for r in rels if r["predicate"] == "overlaps"]
    assert len(overlaps) == 1  # deduped on sorted key


# --------------------------------------------------------------------------- #
# render_vision_context
# --------------------------------------------------------------------------- #
def test_render_contains_all_blocks():
    vlm = {"summary": "a scene", "scene": "test", "ocr": ["hello"]}
    prims = [{"id": "v1", "label": "cat", "box": [0, 0, 100, 100],
              "confidence": 0.9, "grounding": "prompted"}]
    ctx = vt.render_vision_context(vlm, prims, [])
    assert "<vision-context>" in ctx and "</vision-context>" in ctx
    assert "<visual-primitives" in ctx
    assert "visible_text: hello" in ctx


def test_render_budget_trims_prose_not_primitives():
    vlm = {"summary": "x" * 10000}
    prims = [{"id": "v1", "label": "keep", "box": [0, 0, 10, 10],
              "confidence": 1.0, "grounding": "prompted"}]
    ctx = vt.render_vision_context(vlm, prims, [], budget=500)
    assert "<visual-primitives" in ctx  # primitives survive trimming
    assert len(ctx) <= 600  # small slack for tags


# --------------------------------------------------------------------------- #
# analyze — fail-closed (VLM mocked at the HTTP boundary)
# --------------------------------------------------------------------------- #
def test_analyze_fail_closed_after_invalid_vlm(monkeypatch, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)  # any non-empty bytes

    def fake_call(model, messages, **kw):
        return {"choices": [{"message": {"content": "not json at all"}}]}

    monkeypatch.setattr(vt, "_call", fake_call)
    with pytest.raises(RuntimeError, match="fail-closed"):
        vt.analyze(str(img))


def test_analyze_ok_path(monkeypatch, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)

    def fake_call(model, messages, **kw):
        return {"choices": [{"message": {"content": json.dumps({
            "summary": "test image",
            "scene": "test",
            "objects": [{"label": "box", "bbox": [0, 0, 100, 100],
                         "confidence": 0.9}],
            "ocr": ["HELLO"],
        })}}]}

    monkeypatch.setattr(vt, "_call", fake_call)
    ctx = vt.analyze(str(img), question="q")
    assert "<vision-context>" in ctx
    assert "v1" in ctx and "box" in ctx


# --------------------------------------------------------------------------- #
# VLM endpoint config: _base_url + _call key resolution (offline urlopen mock)
# --------------------------------------------------------------------------- #
class _FakeUrlopenResponse:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _mock_urlopen(monkeypatch, seen):
    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return _FakeUrlopenResponse({"ok": True})

    monkeypatch.setattr(vt.urllib.request, "urlopen", fake_urlopen)


def test_call_uses_vision_translate_base_url(monkeypatch):
    monkeypatch.setenv("VISION_TRANSLATE_BASE_URL", "https://example.com/v1/chat/completions")
    monkeypatch.setenv("VISION_TRANSLATE_API_KEY", "sk-vt")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    seen: dict = {}
    _mock_urlopen(monkeypatch, seen)
    assert vt._call("m", [], retries=0) == {"ok": True}
    assert seen["url"] == "https://example.com/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-vt"


def test_call_openrouter_key_backward_compatible(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
    monkeypatch.delenv("VISION_TRANSLATE_API_KEY", raising=False)
    monkeypatch.delenv("VISION_TRANSLATE_BASE_URL", raising=False)

    seen: dict = {}
    _mock_urlopen(monkeypatch, seen)
    assert vt._call("m", [], retries=0) == {"ok": True}
    assert seen["url"] == vt.OR_BASE
    assert seen["auth"] == "Bearer sk-or"


def test_call_new_key_takes_priority(monkeypatch):
    monkeypatch.setenv("VISION_TRANSLATE_API_KEY", "sk-new")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-old")

    seen: dict = {}
    _mock_urlopen(monkeypatch, seen)
    vt._call("m", [], retries=0)
    assert seen["auth"] == "Bearer sk-new"


def test_call_missing_key_mentions_both_names(monkeypatch):
    monkeypatch.delenv("VISION_TRANSLATE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="VISION_TRANSLATE_API_KEY"):
        vt._call("m", [], retries=0)


# --------------------------------------------------------------------------- #
# P0-1: normalize_bbox zero-area check must run after clamp + round
# --------------------------------------------------------------------------- #
def test_normalize_bbox_clamped_zero_area_dropped():
    assert vt.normalize_bbox({"bbox": [1000, 0, 1001, 1000]}) is None


def test_normalize_bbox_native_zero_area_dropped():
    assert vt.normalize_bbox({"bbox": [1000, 0, 1000, 1000]}) is None


def test_normalize_bbox_clamped_but_nonzero_kept():
    warnings = []
    assert vt.normalize_bbox({"bbox": [-5, 0, 5, 10]}, warnings=warnings) == [0, 0, 5, 10]
    assert warnings


# --------------------------------------------------------------------------- #
# P0-2: build_primitives must preserve confidence 0
# --------------------------------------------------------------------------- #
def test_build_primitives_preserves_confidence_zero():
    prims = vt.build_primitives({"objects": [
        {"label": "x", "bbox": [0, 0, 100, 100], "confidence": 0},
    ]})
    assert prims[0]["confidence"] == 0.0


def test_build_primitives_confidence_default_and_invalid():
    missing = vt.build_primitives({"objects": [
        {"label": "x", "bbox": [0, 0, 100, 100]},
    ]})
    assert missing[0]["confidence"] == 1.0
    invalid = vt.build_primitives({"objects": [
        {"label": "x", "bbox": [0, 0, 100, 100], "confidence": "high"},
    ]})
    assert invalid[0]["confidence"] == 1.0


def test_build_primitives_confidence_clamped():
    prims = vt.build_primitives({"objects": [
        {"label": "x", "bbox": [0, 0, 100, 100], "confidence": -0.2},
    ]})
    assert prims[0]["confidence"] == 0.0


# --------------------------------------------------------------------------- #
# P0-3: identical boxes must never produce mutual inside relations
# --------------------------------------------------------------------------- #
def test_relations_identical_boxes_single_inside():
    prims = [
        {"id": "v1", "box": [0, 0, 100, 100]},
        {"id": "v2", "box": [0, 0, 100, 100]},
    ]
    rels = vt.derive_spatial_relations(prims)
    inside = [r for r in rels if r["predicate"] == "inside"]
    assert len(inside) == 1
    assert (inside[0]["subject"], inside[0]["object"]) != ("v2", "v1")


def test_relations_true_containment_is_directional():
    prims = [
        {"id": "v1", "box": [0, 0, 1000, 1000]},
        {"id": "v2", "box": [100, 100, 300, 300]},
    ]
    rels = vt.derive_spatial_relations(prims)
    inside = [r for r in rels if r["predicate"] == "inside"]
    assert any(r["subject"] == "v2" and r["object"] == "v1" for r in inside)


# --------------------------------------------------------------------------- #
# P1-4: render_vision_context must enforce a hard character budget
# --------------------------------------------------------------------------- #
def test_render_budget_hard_cap_with_many_primitives():
    prims = []
    for r in range(4):
        for c in range(4):
            i = r * 4 + c + 1
            x1, y1 = c * 80 + 5, r * 80 + 5
            prims.append({
                "id": f"v{i}", "label": f"object-{i}",
                "box": [x1, y1, x1 + 50, y1 + 50],
                "confidence": 0.5 + i / 100.0, "grounding": "prompted",
            })
    rels = vt.derive_spatial_relations(prims)
    assert len(rels) > 10  # this is the over-budget core case from the review
    ctx = vt.render_vision_context(
        {"summary": "x" * 5000, "scene": "y" * 5000, "ocr": ["z" * 5000]},
        prims, rels, budget=2000,
    )
    assert len(ctx) <= 2000
    assert "<visual-primitives" in ctx


def test_render_empty_context_is_valid():
    ctx = vt.render_vision_context({}, [], [])
    assert "<vision-context>" in ctx
    assert "</vision-context>" in ctx
    assert "<visual-primitives" not in ctx
    assert "<visual-relations" not in ctx


def test_render_single_primitive_not_truncated():
    prims = [{"id": "v1", "label": "cat", "box": [0, 0, 100, 100],
              "confidence": 0.9, "grounding": "prompted"}]
    ctx = vt.render_vision_context({"summary": "scene"}, prims, [])
    assert "v1" in ctx and "cat" in ctx and "image_1: scene" in ctx


def test_render_budget_is_configurable():
    prims = [{"id": "v1", "label": "cat", "box": [0, 0, 100, 100],
              "confidence": 0.9, "grounding": "prompted"}]
    ctx = vt.render_vision_context({"summary": "x" * 5000}, prims, [], budget=300)
    assert len(ctx) <= 300
