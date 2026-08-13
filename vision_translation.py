"""
Vision Bridge (Fancy) — 核心纯函数库
=====================================
图片 -> 辅助 VLM 结构化 JSON -> canonical visual primitives (norm-1000 xyxy)
     -> 程序化空间关系 -> <vision-context> 文本

设计约束（供插件与本 demo 共用）：
- 导入零副作用：无 argparse / 无网络 / 无 print
- 不嵌套调用 DeepSeek —— 只生成 <vision-context>，由主模型推理
- grounding 诚实标注：mimo-v2.5 是 prompted 模型
- 结果带硬上限，primitives/relations 优先，prose 可裁
依赖：标准库 urllib（Pillow 可选，缩放用）
Key：进程环境变量 OPENROUTER_API_KEY（由 Hermes / 调用方加载）
"""
from __future__ import annotations

import base64
import io
import itertools
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

OR_BASE = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_VLM_MODEL = "xiaomi/mimo-v2.5"      # 当前 verified 的辅助视觉模型
MAX_EDGE = 1568                              # VLM 长边上限（缩放，防超 token）
REQUEST_TIMEOUT = 60                         # 工具上下文收紧到 60s
RETRIES = 2                                  # 网络重试
# 结果硬上限（字符）：primitives/relations 优先，超限裁 prose 不裁坐标
RESULT_BUDGET = 2000
# 每张 note 最多保留的 primitive 数（对齐 OpenHanako 16 上限的稳妥值）
MAX_PRIMITIVES = 16
# 坐标契约：norm-1000 xyxy（与 Fancy 方案一致）
COORD = "norm-1000"
BOX_ORDER = "xyxy"
GROUNDING = "prompted"   # 诚实标注：mimo-v2.5 是被 prompt 逼出坐标，非原生 grounding


# --------------------------------------------------------------------------- #
# 图片 -> data URL
# --------------------------------------------------------------------------- #
def image_to_data_url(path: str, max_edge: int = MAX_EDGE) -> str:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"图片不存在: {path}")
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        data = f.read()
    if not data:
        raise ValueError(f"图片为空: {path}")
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)   # 应用 EXIF 方向（竖拍不横）
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
        pass  # 无 Pillow 也允许原样发送
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


# --------------------------------------------------------------------------- #
# OpenRouter 调用（纯 stdlib，重试 + 退避）
# --------------------------------------------------------------------------- #
def _call(model: str, messages: list, *, json_mode: bool = False, retries: int = RETRIES) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("缺少 OPENROUTER_API_KEY 环境变量")
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
    raise RuntimeError(f"调用失败: {last_err}")


def _extract_text(resp: dict) -> str:
    try:
        return resp["choices"][0]["message"]["content"] or ""
    except Exception:
        return ""


_EMPTY_CTX = {
    "summary": "", "scene": "", "ocr": [],
    "primitives": [], "relations": [], "vlm_json": {},
    "grounding": GROUNDING, "coord": COORD, "box_order": BOX_ORDER,
}


# --------------------------------------------------------------------------- #
# Fancy 核心：结构解析 + 归一化 + 关系 + 渲染
# --------------------------------------------------------------------------- #
def parse_json_tolerant(raw: str) -> dict:
    """剥 JSON fence + 容错解析。失败返回空 dict。"""
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


def normalize_bbox(obj: dict) -> Optional[List[int]]:
    """只做契约内 round/clamp：假定已按 norm-1000 xyxy 返回。

    不做 magnitude 启发式（此前 W/H=0 使像素分支成死代码、≤10 会误丢小框）。
    契约化的方式：VLM 生成 prompt 明确要求 0-1000 xyxy，这里只校验。
    拒绝零面积/越界校正。
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
    if any(v is None or (isinstance(v, float) and v != v) for v in (x1, y1, x2, y2)):
        return None
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    x1, y1 = max(0.0, min(1000.0, x1)), max(0.0, min(1000.0, y1))
    x2, y2 = max(0.0, min(1000.0, x2)), max(0.0, min(1000.0, y2))
    if x2 - x1 < 0.5 or y2 - y1 < 0.5:
        return None
    return [round(x1), round(y1), round(x2), round(y2)]


def build_primitives(vlm_json: dict, max_objects: int = MAX_PRIMITIVES) -> List[dict]:
    """把 VLM 结构化 objects 转成 canonical primitives，按 confidence 排序截断。"""
    primitives: List[dict] = []
    objs = vlm_json.get("objects") or vlm_json.get("entities") or vlm_json.get("visual_primitives") or []
    if not isinstance(objs, list):
        objs = []
    for i, o in enumerate(objs):
        if not isinstance(o, dict):
            continue
        label = o.get("label") or o.get("name") or o.get("ref") or o.get("class") or f"obj{i}"
        box = normalize_bbox(o)
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
    # confidence 降序 + 截断
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
    """A 被 B 包含的比例 intersection(A,B)/area(A)。"""
    inter = _intersection(a, b)
    if not inter or _area(a) <= 0:
        return 0.0
    return _area(inter) / _area(a)


EPS = 20  # norm-1000 units


def derive_spatial_relations(prims: List[dict]) -> List[dict]:
    """纯程序化几何关系，source=geometry，去重、防矛盾。"""
    rels: List[dict] = []
    ids = [p["id"] for p in prims]
    idx = {p["id"]: p for p in prims}
    seen = set()

    def add(subject, predicate, object, source="geometry", confidence=1.0):
        # 方向无关谓词（overlaps）去重：alphabetical 排序做键
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
        # 横向 / 纵向（仅当严格分离时）
        if A[2] + EPS < B[0]:
            add(a, "left_of", b)
        elif B[2] + EPS < A[0]:
            add(a, "right_of", b)
        if A[3] + EPS < B[1]:
            add(a, "above", b)
        elif B[3] + EPS < A[1]:
            add(a, "below", b)
        # 包含（方向正确：A inside B 当 A 大部分落在 B 内）
        ca = _containment(A, B)
        cb = _containment(B, A)
        if ca >= 0.90:
            add(a, "inside", b)
        elif cb >= 0.90:
            add(b, "inside", a)
        elif 0.10 <= _iou(A, B) < 0.90:
            add(a, "overlaps", b, confidence=_iou(A, B))
    return rels


def _clip_to_budget(text: str, budget: int) -> str:
    """按字符预算截断，尾部加提示。"""
    if len(text) <= budget:
        return text
    return text[: max(0, budget - 10)] + "…[截断]"


def render_vision_context(vlm_json: dict, prims: List[dict], rels: List[dict],
                          question: str = "", budget: int = RESULT_BUDGET) -> str:
    """生成 <vision-context>。primitives/relations 优先，prose 可裁。"""
    note = (vlm_json.get("summary") or "").strip()
    scene = (vlm_json.get("scene") or "").strip()
    ocr = vlm_json.get("ocr") or vlm_json.get("visible_text") or []
    if isinstance(ocr, str):
        ocr = [ocr]
    ocr_str = "; ".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in ocr)

    # 1) primitives / relations（优先保留，单独算预算）
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

    # 2) prose（可裁）
    prose_lines = []
    if note:
        prose_lines.append(f"image_1: {note}")
    if scene:
        prose_lines.append(f"scene: {scene}")
    if ocr_str:
        prose_lines.append(f"visible_text: {ocr_str}")
    prose = "\n".join(prose_lines)

    # 3) 组装：primitives/relations 前置且保底，prose 最后（可裁）
    core = "\n".join(x for x in [prim_block, rel_block] if x)
    body_lines = []
    if core:
        body_lines.append(core)
    if prose:
        body_lines.append(prose)
    if question:
        body_lines.append(f"user_request: {question}")
    body = "\n".join(body_lines)

    # 若整体超预算，优先裁 prose（primitives/relations 已在其前方）
    if len(body) > budget:
        # primitives/relations 固定保留，只裁后半 prose
        header = core
        trail = "\n\n".join(x for x in [prose, f"user_request: {question}"] if x)
        keep = max(0, budget - len(header) - 3)
        trail = trail[:keep] + "…[截断]"
        body = "\n\n".join(x for x in [header, trail] if x)

    return f"<vision-context>\n{body}\n</vision-context>"


# --------------------------------------------------------------------------- #
# 主入口：analyze(path, question=None) -> <vision-context> 文本
# 失败 raise（调用方决定降级策略）。
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
        raise RuntimeError("VLM 连续 3 次返回非法 JSON —— fail-closed：未看到图片，不注入空上下文")

    prims = build_primitives(vlm_json, max_objects=max_objects)
    rels = derive_spatial_relations(prims)
    return render_vision_context(vlm_json, prims, rels, question=question)
