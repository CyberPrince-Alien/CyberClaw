"""Image generation tool using OpenAI DALL-E or Stability AI."""

import base64
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def image_generate_handler(
    prompt: str,
    provider: str = "dall-e",
    model: str = "dall-e-3",
    size: str = "1024x1024",
    quality: str = "standard",
    save_path: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> str:
    """Generate an image from a text prompt.

    Providers:
    - dall-e: Uses OpenAI DALL-E API
    - stability: Uses Stability AI API
    """
    import httpx

    if provider == "dall-e":
        return await _generate_dalle(prompt, model, size, quality, save_path, api_key)
    elif provider == "stability":
        return await _generate_stability(prompt, size, save_path, api_key)
    else:
        return f"Unknown image provider: {provider}. Use 'dall-e' or 'stability'."


async def _generate_dalle(
    prompt: str, model: str, size: str, quality: str,
    save_path: str | None, api_key: str | None,
) -> str:
    """Generate via OpenAI DALL-E API."""
    import httpx

    if not api_key:
        import os
        api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return "Error: No OpenAI API key. Set OPENAI_API_KEY or provide api_key."

    url = "https://api.openai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "response_format": "b64_json" if save_path else "url",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body, headers=headers, timeout=60)
        if resp.status_code != 200:
            return f"DALL-E error ({resp.status_code}): {resp.text[:300]}"

        result = resp.json()
        data = result.get("data", [{}])[0]

        if save_path and "b64_json" in data:
            img_bytes = base64.b64decode(data["b64_json"])
            out_path = Path(save_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(img_bytes)
            return f"Image saved to {save_path} ({len(img_bytes)} bytes)"

        url_result = data.get("url", "")
        revised_prompt = data.get("revised_prompt", "")
        return f"Image generated:\n  URL: {url_result}\n  Revised prompt: {revised_prompt}"


async def _generate_stability(
    prompt: str, size: str, save_path: str | None, api_key: str | None,
) -> str:
    """Generate via Stability AI API."""
    import httpx

    if not api_key:
        import os
        api_key = os.environ.get("STABILITY_API_KEY", "")
    if not api_key:
        return "Error: No Stability API key. Set STABILITY_API_KEY or provide api_key."

    # Parse size
    try:
        w, h = size.split("x")
        width, height = int(w), int(h)
    except ValueError:
        width, height = 1024, 1024

    url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "text_prompts": [{"text": prompt, "weight": 1}],
        "cfg_scale": 7,
        "width": width,
        "height": height,
        "samples": 1,
        "steps": 30,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body, headers=headers, timeout=60)
        if resp.status_code != 200:
            return f"Stability error ({resp.status_code}): {resp.text[:300]}"

        result = resp.json()
        artifacts = result.get("artifacts", [])
        if not artifacts:
            return "No image generated"

        img_b64 = artifacts[0].get("base64", "")
        if save_path and img_b64:
            img_bytes = base64.b64decode(img_b64)
            out_path = Path(save_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(img_bytes)
            return f"Image saved to {save_path} ({len(img_bytes)} bytes)"

        return f"Image generated ({len(img_b64)} base64 chars). Use save_path to save to disk."


IMAGE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": "Generate an image from a text description using DALL-E or Stability AI.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the image to generate",
                },
                "provider": {
                    "type": "string",
                    "enum": ["dall-e", "stability"],
                    "description": "Image generation provider",
                    "default": "dall-e",
                },
                "size": {
                    "type": "string",
                    "enum": ["256x256", "512x512", "1024x1024", "1024x1792", "1792x1024"],
                    "description": "Image size",
                    "default": "1024x1024",
                },
                "save_path": {
                    "type": "string",
                    "description": "File path to save the image (optional)",
                },
            },
            "required": ["prompt"],
        },
    },
}
