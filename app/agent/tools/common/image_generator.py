# app/agent/tools/common/image_generator.py
"""
图片生成 Tool

使用 OpenAI 兼容的 API 根据文本描述生成图片。
支持 DALL-E 3 以及其他 OpenAI 兼容的图片生成服务。
生成后自动上传到 imgbb 图床进行持久化存储。
"""

import asyncio
import logging
from typing import Any

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.utils.image_storage import upload_to_imgbb

logger = logging.getLogger(__name__)


SILICONFLOW_IMAGE_SIZES = {
    "1024x1024": "1024x1024",
    "1024x768": "1024x768",
    "768x1024": "768x1024",
    "1024x576": "1024x576",
    "576x1024": "576x1024",
    "512x512": "512x512",
}


def _is_siliconflow_config(base_url: str | None, model: str) -> bool:
    return "siliconflow" in (base_url or "").lower() or model.startswith("Tongyi-MAI/")


def _normalize_siliconflow_size(size: str) -> str:
    """Map common OpenAI image sizes to SiliconFlow-supported sizes."""
    if size == "auto":
        return "1024x1024"
    if size in SILICONFLOW_IMAGE_SIZES:
        return size
    if size in {"1536x1024", "1792x1024"}:
        return "1024x768"
    if size in {"1024x1536", "1024x1792"}:
        return "768x1024"
    return "1024x1024"


def _extract_siliconflow_image_url(payload: dict[str, Any]) -> str | None:
    images = payload.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return first.get("url")
    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first.get("url")
    return None


class ImageGeneratorTool(BaseTool):
    """
    图片生成 Tool。

    使用 OpenAI 兼容的 API 根据文本描述生成图片。
    支持 DALL-E 3 以及其他 OpenAI 兼容的图片生成服务。
    生成后自动上传到 imgbb 图床进行持久化存储。
    """

    name = "image_generator"
    description = "根据文本描述生成图片，并返回可访问的图片 URL。"
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "图片描述，尽量具体（主体、风格、场景、构图）",
            },
            "size": {
                "type": "string",
                "enum": ["auto", "1024x1024", "1536x1024", "1024x1536", "256x256", "512x512", "1792x1024", "1024x1792"],
                "default": "1536x1024",
                "description": "图片尺寸（宽x高）",
            },
            "quality": {
                "type": "string",
                "enum": ["standard", "hd", "auto"],
                "default": "standard",
                "description": "图片质量：standard 标准，hd 高清，auto 自动",
            },
            "style": {
                "type": "string",
                "enum": ["vivid", "natural"],
                "default": "vivid",
                "description": "图片风格：vivid 生动，natural 自然",
            },
        },
        "required": ["prompt"],
    }

    async def execute(
        self,
        prompt: str = "",
        size: str = "1024x1024",
        quality: str = "standard",
        style: str = "vivid",
        **kwargs,
    ) -> ToolResult:
        """生成图片并上传到 imgbb 持久化存储。"""
        if not prompt:
            return ToolResult(success=False, error="Prompt is required")

        try:
            from app.config import settings

            config = settings.image_generation
            api_key = config.api_key
            if not api_key:
                return ToolResult(
                    success=False,
                    error="Image generation API key is not configured",
                )

            if not config.enabled:
                return ToolResult(
                    success=False,
                    error="Image generation is disabled",
                )

            revised_prompt = None
            if _is_siliconflow_config(config.base_url, config.model):
                import httpx

                base_url = (config.base_url or "https://api.siliconflow.cn/v1").rstrip("/")
                image_size = _normalize_siliconflow_size(size)
                logger.info(
                    "Generating image via SiliconFlow: model=%s image_size=%s",
                    config.model,
                    image_size,
                )
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(120.0, connect=10.0)
                ) as client:
                    response = await client.post(
                        f"{base_url}/images/generations",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": config.model,
                            "prompt": prompt,
                            "image_size": image_size,
                            "batch_size": 1,
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()

                original_url = _extract_siliconflow_image_url(payload)
            else:
                from openai import AsyncOpenAI

                # Create client with optional base_url for OpenAI-compatible APIs
                client_kwargs = {"api_key": api_key, "timeout": 120.0}
                if config.base_url:
                    client_kwargs["base_url"] = config.base_url

                client = AsyncOpenAI(
                    **client_kwargs, # type: ignore
                )

                # Generate image
                response = await client.images.generate(
                    model=config.model,
                    prompt=prompt,
                    size=size, # type: ignore
                    quality=quality, # type: ignore
                    style=style, # type: ignore
                    n=1,
                )

                # Get the generated image URL
                image_data = response.data[0] # type: ignore
                original_url = image_data.url
                revised_prompt = image_data.revised_prompt

            if not original_url:
                return ToolResult(
                    success=False,
                    error="Image generation returned no URL",
                )

            # Upload to imgbb for persistent storage
            try:
                storage_result = await asyncio.wait_for(
                    upload_to_imgbb(original_url),
                    timeout=25.0,
                )
            except asyncio.TimeoutError:
                logger.warning("imgbb upload timed out, using original image URL")
                storage_result = None

            if storage_result:
                # Use imgbb URL as the final URL
                return ToolResult(
                    success=True,
                    data={
                        "prompt": prompt,
                        "url": storage_result["url"],
                        "display_url": storage_result["display_url"],
                        "thumb_url": storage_result.get("thumb_url"),
                        "revised_prompt": revised_prompt,
                        "storage": "imgbb",
                    },
                )
            else:
                # Fallback to original URL if upload fails
                logger.warning("imgbb upload failed, using original URL")
                return ToolResult(
                    success=True,
                    data={
                        "prompt": prompt,
                        "url": original_url,
                        "revised_prompt": revised_prompt,
                        "storage": "original",
                    },
                )

        except ImportError:
            return ToolResult(
                success=False,
                error="openai package is not installed. Run: pip install openai",
            )
        except Exception as e:
            logger.exception(f"Image generation failed: {e}")
            return ToolResult(success=False, error=f"Image generation failed: {str(e)}")


__all__ = ["ImageGeneratorTool"]
