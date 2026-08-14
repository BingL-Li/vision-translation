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
