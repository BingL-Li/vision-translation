"""
Translation with Visual Primitives — import-pure core library
=============================================================
image -> auxiliary VLM structured JSON -> canonical visual primitives
    (norm-1000 xyxy) -> programmatic spatial relations -> <vision-context> text

Design constraints (shared by the plugin and the CLI demo):
- Zero side effects at import: no argparse, no network, no prints.
- No nested text-LLM call: this module only produces <vision-context>;
  the main model does the reasoning.
- Honest grounding: the auxiliary VLM is prompted to emit boxes
  (grounding: prompted), not a native detector.
- Hard output caps: primitives/relations survive budget trimming, prose is cut.
Dependencies: stdlib urllib only (Pillow optional, used for downscaling).
Key: OPENROUTER_API_KEY from the process environment (loaded by Hermes/caller).
"""

from __future__ import annotations

import base64
import io
import itertools
import json
import math
import mimetypes
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

OR_BASE = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_VLM_MODEL = "xiaomi/mimo-v2.5"      # verified auxiliary vision model
MAX_EDGE = 1568                              # VLM long-edge cap (downscale guard)
REQUEST_TIMEOUT = 60                         # tool context tightened to 60s
RETRIES = 2                                  # network retries
# Hard result cap (chars): primitives/relations first, prose trimmed last.
RESULT_BUDGET = 2000
# Max primitives kept per image (deliberately conservative, aligned with 16)
MAX_PRIMITIVES = 16
# Coordinate contract: image space normalized to 1000x1000.
COORD = "norm-1000"
BOX_ORDER = "xyxy"
GROUNDING = "prompted"   # honest: mimo-v2.5 is prompted for boxes, not native


# --------------------------------------------------------------------------- #
# image -> data URL
# --------------------------------------------------------------------------- #
def image_to_data_url(path: str, max_edge: int = MAX_EDGE) -> str:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"image not found: {path}")
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        data = f.read()
    if not data:
        raise ValueError(f"empty image: {path}")
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)   # honor EXIF orientation
        img = img.convert("RGB")
        w, h = img.size
        scale = min(1.0, max_edge / max(w, h))
        if scale < 1.0:
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        data = buf.getvalue()
        mime = "image/jpeg"
    except Exception:
        pass  # Pillow optional: send the original bytes as-is
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


# --------------------------------------------------------------------------- #
# OpenRouter call (pure stdlib, retries + backoff)
# --------------------------------------------------------------------------- #
def _call(model: str, messages: list, *, json_mode: bool = False, retries: int = RETRIES) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable is not set")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages, "max_tokens": 4096}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(OR_BASE, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    if isinstance(last_err, urllib.error.HTTPError):
        body = last_err.read().decode("utf-8", "replace")
        raise RuntimeError(f"OpenRouter HTTP {last_err.code}: {body[:300]}")
    raise RuntimeError(f"OpenRouter call failed: {last_err}")


def complete_text(model: str, messages: list) -> dict:
    """Public chat-completion wrapper (CLI/demo use). Returns the raw response dict."""
    return _call(model, messages)


def _extract_text(resp: dict) -> str:
    try:
        return resp["choices"][0]["message"]["content"] or ""
    except Exception:
        return ""


def extract_text(resp: dict) -> str:
    """Public accessor: pull the assistant text out of a completion response."""
    return _extract_text(resp)


_EMPTY_CTX = {
    "summary": "", "scene": "", "ocr": [],
    "primitives": [], "relations": [], "vlm_json": {},
    "grounding": GROUNDING, "coord": COORD, "box_order": BOX_ORDER,
}


# --------------------------------------------------------------------------- #
# Core: tolerant parsing, normalization, relations, rendering
# --------------------------------------------------------------------------- #
def parse_json_tolerant(raw: str) -> dict:
    """Strip JSON fences and parse tolerantly. Returns {} on failure."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except Exception:
        a, b = raw.find("{"), raw.rfind("}")
        if a != -1 and b > a:
            try:
                return json.loads(raw[a:b + 1])
            except Exception:
                pass
    return {}


def normalize_bbox(obj: dict, warnings: Optional[List[str]] = None) -> Optional[List[int]]:
    """Validate/clamp a box against the norm-1000 xyxy contract.

    Contract-based (not heuristic): the VLM prompt demands 0-1000 xyxy; here we
    only validate. Out-of-contract values are clamped (with an optional warning
    recorded into ``warnings``); zero-area / non-finite boxes are dropped.
    """
    b = obj.get("bbox") or obj.get("box") or obj.get("coordinates") or obj.get("xyxy")
    if not b:
        return None
    if isinstance(b, dict):
        b = [b.get("x1"), b.get("y1"), b.get("x2"), b.get("y2")]
    try:
        x1, y1, x2, y2 = [float(v) for v in (b[0], b[1], b[2], b[3])]
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
        return None
    raw = (x1, y1, x2, y2)
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    if x2 - x1 < 0.5 or y2 - y1 < 0.5:
        return None  # zero-area box
    if warnings is not None:
        outside = [v for v in raw if v < 0 or v > 1000]
        if outside:
            warnings.append(
                f"bbox {[round(v, 1) for v in raw]} outside norm-1000 contract "
                f"(possible pixel-space output from the VLM)"
            )
    return [
        round(max(0.0, min(1000.0, x1))), round(max(0.0, min(1000.0, y1))),
        round(max(0.0, min(1000.0, x2))), round(max(0.0, min(1000.0, y2))),
    ]


def build_primitives(vlm_json: dict, max_objects: int = MAX_PRIMITIVES,
                     warnings: Optional[List[str]] = None) -> List[dict]:
    """Turn VLM structured objects into canonical primitives, sorted by
    confidence and truncated to ``max_objects``."""
    primitives: List[dict] = []
    objs = vlm_json.get("objects") or vlm_json.get("entities") or vlm_json.get("visual_primitives") or []
    if not isinstance(objs, list):
        objs = []
    for i, o in enumerate(objs):
        if not isinstance(o, dict):
            continue
        label = o.get("label") or o.get("name") or o.get("ref") or o.get("class") or f"obj{i}"
        box = normalize_bbox(o, warnings=warnings)
        if box is None:
            continue
        try:
            conf = float(o.get("confidence") or o.get("conf") or 1.0)
        except (TypeError, ValueError):
            conf = 1.0
        conf = max(0.0, min(1.0, conf))
        primitives.append({
            "id": f"v{i + 1}", "label": str(label)[:96], "box": box,
            "confidence": conf, "grounding": GROUNDING,
        })
    primitives.sort(key=lambda p: p["confidence"], reverse=True)
    return primitives[:max_objects]


def _area(b: List[int]) -> float:
    return max(0.0, (b[2] - b[0]) * (b[3] - b[1]))


def _intersection(a: List[int], b: List[int]) -> Optional[List[int]]:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    return [x1, y1, x2, y2] if (x2 > x1 and y2 > y1) else None


def _iou(a: List[int], b: List[int]) -> float:
    inter = _intersection(a, b)
    if not inter:
        return 0.0
    ia = _area(inter)
    denom = _area(a) + _area(b) - ia
    return ia / denom if denom > 0 else 0.0


def _containment(a: List[int], b: List[int]) -> float:
    """Fraction of A that lies inside B: intersection(A,B) / area(A)."""
    inter = _intersection(a, b)
    if not inter or _area(a) <= 0:
        return 0.0
    return _area(inter) / _area(a)


EPS = 20  # norm-1000 units


def derive_spatial_relations(prims: List[dict]) -> List[dict]:
    """Pure geometric relations, source=geometry; deduped and contradiction-free
    by construction (directional predicates only fire when strictly separated)."""
    rels: List[dict] = []
    ids = [p["id"] for p in prims]
    idx = {p["id"]: p for p in prims}
    seen = set()

    def add(subject, predicate, object, source="geometry", confidence=1.0):
        # Direction-agnostic predicates (overlaps) dedupe on a sorted key.
        key = tuple(sorted([subject, object])) if predicate == "overlaps" else (subject, predicate, object)
        if key in seen:
            return
        seen.add(key)
        rels.append({"subject": subject, "predicate": predicate, "object": object,
                     "source": source, "confidence": round(confidence, 2)})

    for a, b in itertools.permutations(ids, 2):
        A, B = idx[a]["box"], idx[b]["box"]
        if not A or not B:
            continue
        # Horizontal / vertical (only when strictly separated)
        if A[2] + EPS < B[0]:
            add(a, "left_of", b)
        elif B[2] + EPS < A[0]:
            add(a, "right_of", b)
        if A[3] + EPS < B[1]:
            add(a, "above", b)
        elif B[3] + EPS < A[1]:
            add(a, "below", b)
        # Containment (direction-aware: A inside B when A mostly falls in B)
        ca = _containment(A, B)
        cb = _containment(B, A)
        if ca >= 0.90:
            add(a, "inside", b)
        elif cb >= 0.90:
            add(b, "inside", a)
        elif 0.10 <= _iou(A, B) < 0.90:
            add(a, "overlaps", b, confidence=_iou(A, B))
    return rels


def render_vision_context(vlm_json: dict, prims: List[dict], rels: List[dict],
                          question: str = "", budget: int = RESULT_BUDGET,
                          warnings: Optional[List[str]] = None) -> str:
    """Render <vision-context>. Primitives/relations are protected; prose and
    warnings are the first to be trimmed when over budget."""
    note = (vlm_json.get("summary") or "").strip()
    scene = (vlm_json.get("scene") or "").strip()
    ocr = vlm_json.get("ocr") or vlm_json.get("visible_text") or []
    if isinstance(ocr, str):
        ocr = [ocr]
    ocr_str = "; ".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in ocr)

    # 1) primitives / relations (always kept; budgeted separately)
    prim_block = ""
    if prims:
        lines = [f'<visual-primitives coord="{COORD}" box_order="{BOX_ORDER}" grounding="{GROUNDING}">']
        for p in prims:
            bx = f"[{p['box'][0]}, {p['box'][1]}, {p['box'][2]}, {p['box'][3]}]"
            lines.append(f"- {p['id']} | type: box | box: {bx} | ref: {p['label']} | confidence: {p['confidence']} | grounding: {GROUNDING}")
        lines.append("</visual-primitives>")
        prim_block = "\n".join(lines)
    rel_block = ""
    if rels:
        lines = ["<visual-relations>"]
        for r in rels:
            lines.append(f"- {r['subject']} {r['predicate']} {r['object']} | source: {r['source']} | confidence: {r['confidence']}")
        lines.append("</visual-relations>")
        rel_block = "\n".join(lines)

    # 2) prose + warnings (trimmed first)
    prose_lines = []
    if note:
        prose_lines.append(f"image_1: {note}")
    if scene:
        prose_lines.append(f"scene: {scene}")
    if ocr_str:
        prose_lines.append(f"visible_text: {ocr_str}")
    if warnings:
        prose_lines.append("vision_warnings: " + "; ".join(warnings))
    prose = "\n".join(prose_lines)

    # 3) assemble: primitives/relations up front and protected, prose last
    core = "\n".join(x for x in [prim_block, rel_block] if x)
    body_lines = []
    if core:
        body_lines.append(core)
    if prose:
        body_lines.append(prose)
    if question:
        body_lines.append(f"user_request: {question}")
    body = "\n".join(body_lines)

    # Over budget: keep primitives/relations, trim the trailing prose part.
    if len(body) > budget:
        header = core
        trail = "\n\n".join(x for x in [prose, f"user_request: {question}"] if x)
        keep = max(0, budget - len(header) - 3)
        trail = trail[:keep] + "…[truncated]"
        body = "\n\n".join(x for x in [header, trail] if x)

    return f"<vision-context>\n{body}\n</vision-context>"


# --------------------------------------------------------------------------- #
# Main entry: analyze(path, question=None) -> <vision-context> text
# Raises on failure (the caller decides the fallback strategy).
# --------------------------------------------------------------------------- #
def analyze(image_path: str, question: str = "", model: str = DEFAULT_VLM_MODEL,
            max_objects: int = MAX_PRIMITIVES) -> str:
    data_url = image_to_data_url(image_path)
    prompt = (
        "你是视觉 grounding 引擎。请严格分析图片并 ONLY 返回合法 JSON，不要任何额外文字。\n"
        "JSON 结构（全部字段必填）：\n"
        "{\n"
        '  "summary": "一句话概述整张图片",\n'
        '  "scene": "场景/类别",\n'
        '  "objects": [{"label": "物体名", "bbox": [x1,y1,x2,y2], "confidence": 0.0}],\n'
        '  "ocr": ["图片中所有清晰可辨的文字，逐条"]\n'
        "}\n"
        f"要求：objects 里的 bbox 用 {COORD} 屏幕归一化坐标系（左上0,0 右下1000,1000），"
        f"用 {BOX_ORDER} 顺序，覆盖图中所有主要物体。"
        "ocr 尽量完整，包括小字、侧栏、菜单、含 emoji。无法确定的内容不要编造。"
        "若无对象则 objects 输出空数组 []。"
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": [
            {"type": "text", "text": question or "识别这张图片并输出 JSON。"},
            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
        ]},
    ]
    vlm_json: Dict[str, Any] = {}
    for attempt in range(3):
        resp = _call(model, messages, json_mode=(attempt == 0))
        vlm_json = parse_json_tolerant(_extract_text(resp))
        if vlm_json.get("summary") or vlm_json.get("objects"):
            break
        vlm_json = {}
    if not (vlm_json.get("summary") or vlm_json.get("objects")):
        raise RuntimeError(
            "VLM returned invalid JSON 3 times — fail-closed: refusing to "
            "inject an empty or fabricated context"
        )

    warnings: List[str] = []
    prims = build_primitives(vlm_json, max_objects=max_objects, warnings=warnings)
    rels = derive_spatial_relations(prims)
    return render_vision_context(vlm_json, prims, rels, question=question, warnings=warnings)
