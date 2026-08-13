"""vision-translation plugin — Translation with Visual Primitives（视觉原语翻译层）。

注册一个工具型插件：``vision_translate``。

命名：对仗 DeepSeek 论文《Thinking with Visual Primitives》——论文让模型内生
"用视觉原语思考"，本插件反其道而行：由外挂层把视觉原语**翻译**成文本注入，
主模型（DeepSeek 等纯文本）保持不动。外挂、通用、模型无关。

职责边界（参考 OpenHanako Vision Bridge）：
  图片 -> 辅助 VLM 结构化 JSON -> canonical primitives (norm-1000 xyxy)
       -> 程序化空间关系 -> <vision-context> 文本
  工具 **只返回** <vision-context>，不嵌套调用任何文本 LLM ——
  由当前 Hermes 主模型（本身就是 DeepSeek）直接推理。

区别于内置 vision_analyze：
  - 内置：一句话看图描述（便宜）
  - 本工具：需要 bbox 坐标 / 空间关系 / 结构化实体 / OCR 时使用
    例如"谁在谁右边""有几个 X""UI 元素定位""图纸元件 bbox"。
"""
from __future__ import annotations

import os
from pathlib import Path

from . import vision_translation as vt

TOOL_NAME = "vision_translate"
TOOLSET = "vision_translation"
EMOJI = "🧭"
_MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25MB 防呆上限


_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Translation with Visual Primitives：把图片翻译成结构化视觉原语上下文"
        "（对象 bbox 坐标 / 空间关系 / OCR / 场景摘要），返回 <vision-context> 文本。"
        "当需要**坐标、位置关系、计数、UI 元素或图纸元件定位、结构化实体**时使用本工具；"
        "只需要一句话看图描述时用内置 vision_analyze 更便宜。"
        "图片会发送给 OpenRouter 辅助视觉模型。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "本地图片路径（必填）。会自动 expanduser。",
            },
            "question": {
                "type": "string",
                "description": "针对图片的问题（可选）。用于引导解析重点。",
            },
            "max_objects": {
                "type": "integer",
                "description": "最多保留的对象数（可选，默认 12）。",
            },
        },
        "required": ["image_path"],
    },
}


def _handler(args: dict, **kw) -> str:
    """同步 handler。失败返回错误文本（不 raise 导致整轮中断），保持 fail-closed 语义。"""
    image_path = str(args.get("image_path") or "").strip()
    question = str(args.get("question") or "").strip()
    try:
        max_objects = int(args.get("max_objects") or 12)
    except (TypeError, ValueError):
        max_objects = 12
    max_objects = max(1, min(max_objects, vt.MAX_PRIMITIVES))

    if not image_path:
        return '{"success": false, "error": "缺少 image_path"}'
    p = Path(image_path).expanduser()
    if not p.is_file():
        return f'{{"success": false, "error": "图片不存在: {p}"}}'
    try:
        if p.stat().st_size > _MAX_IMAGE_BYTES:
            return f'{{"success": false, "error": "图片过大(>{_MAX_IMAGE_BYTES//(1024*1024)}MB)"}}'
    except OSError as e:
        return f'{{"success": false, "error": "无法访问图片: {e}"}}'

    # 模型：先看环境覆盖，否则回落已验证默认值（不硬编码为用户配置之外的东西）
    model = os.environ.get("VISION_TRANSLATE_VLM", vt.DEFAULT_VLM_MODEL)

    try:
        ctx = vt.analyze(str(p), question=question, model=model, max_objects=max_objects)
    except Exception as e:
        # fail-closed：不注入空/伪造上下文，把错误交给 agent 决定是否回退 vision_analyze
        return (
            '<vision-context>\n'
            f'{{"status": "unavailable", "error": "视觉解析失败: {e}"}}\n'
            "</vision-context>"
        )

    # 只返回 <vision-context>，无冗余副本；标注来源模型便于 agent 判断
    return (
        f"<vision-source model=\"{model}\" coord=\"{vt.COORD}\" box_order=\"{vt.BOX_ORDER}\" "
        f"grounding=\"{vt.GROUNDING}\"/>\n{ctx}"
    )


def _check_available() -> bool:
    """依赖门控：需要 OpenRouter key 才能工作。"""
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def register(ctx) -> None:
    ctx.register_tool(
        name=TOOL_NAME,
        toolset=TOOLSET,
        schema=_SCHEMA,
        handler=_handler,
        check_fn=_check_available,
        requires_env=["OPENROUTER_API_KEY"],
        is_async=False,
        description=_SCHEMA["description"],
        emoji=EMOJI,
    )
