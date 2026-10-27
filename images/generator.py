from __future__ import annotations
import os
import sys
import shutil
import base64
import time
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont

try:
    from gradio_client import Client
except ImportError:
    Client = None

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from logger import setup_logger, log_step

logger = setup_logger("images")

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080

DEFAULT_NEGATIVE_PROMPT = (
    "low quality, worst quality, deformed, bad anatomy, bad hands, missing fingers, extra digits, "
    "blurry, mutated, text, watermark, signature, speech bubble"
)

_gradio_client = None


def get_animagine_client():
    """Connect to Animagine XL 3.1 via Private Google Colab (Unlimited) or HF ZeroGPU Space (90s Free Tier)."""
    global _gradio_client
    if _gradio_client is None and Client is not None:
        # 1. Check for private Google Colab GPU backend (Unlimited mode)
        colab_url = os.environ.get("ANIMAGINE_URL") or os.environ.get("COLAB_GRADIO_URL")
        if colab_url:
            colab_url = colab_url.strip().rstrip("/")
            try:
                logger.info(f"Connecting to Private Google Colab GPU Backend (Unlimited Mode): {colab_url} ...")
                _gradio_client = Client(colab_url)
                logger.info(f"✔ Connected to Colab GPU Backend successfully! (Zero quota limits)")
                return _gradio_client
            except Exception as e:
                logger.warning(f"Failed to connect to Colab URL ({colab_url}): {e}. Falling back to HF Space.")

        # 2. Public Hugging Face ZeroGPU Space (Standard 90s daily quota mode)
        token = os.environ.get("huggingface_colab") or os.environ.get("HF_TOKEN")
        try:
            if token:
                logger.info("Connecting to Animagine XL 3.1 Space (90s Free ZeroGPU Tier, with HF token)...")
                _gradio_client = Client("cagliostrolab/animagine-xl-3.1", token=token)
            else:
                logger.info("Connecting to Animagine XL 3.1 Space (90s Free ZeroGPU Tier, anonymous)...")
                _gradio_client = Client("cagliostrolab/animagine-xl-3.1")
            logger.info("✔ Connected to Animagine XL 3.1 Space successfully.")
        except Exception as e:
            logger.warning(f"Could not connect to Animagine XL Space directly: {e}")
            try:
                _gradio_client = Client("cagliostrolab/animagine-xl-3.1")
            except Exception:
                _gradio_client = None
    return _gradio_client


def _create_cinematic_fallback(prompt: str, out_path: Path):
    """Create a high-resolution dark aesthetic backdrop if external APIs are exhausted."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), color=(15, 18, 30))
    draw = ImageDraw.Draw(img)
    
    # Subtle gradient bands
    for y in range(VIDEO_HEIGHT):
        r = int(15 + (y / VIDEO_HEIGHT) * 15)
        g = int(18 + (y / VIDEO_HEIGHT) * 20)
        b = int(30 + (y / VIDEO_HEIGHT) * 35)
        draw.line([(0, y), (VIDEO_WIDTH, y)], fill=(r, g, b))

    # Center label
    summary_text = prompt[:80] + "..." if len(prompt) > 80 else prompt
    try:
        font = ImageFont.truetype("arial.ttf", 36)
        small_font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        font = ImageFont.load_default()
        small_font = font

    draw.text((100, VIDEO_HEIGHT // 2 - 40), f"Scene: {summary_text}", fill=(200, 220, 255), font=font)
    draw.text((100, VIDEO_HEIGHT // 2 + 20), "(Visual Render - Run animagine_colab.ipynb or connect HF Pro for continuous diffusion)", fill=(120, 140, 180), font=small_font)
    img.save(out_path, format="JPEG", quality=95)


def generate_single_image(
    prompt: str,
    out_path: Path,
    seed: int = 42,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
) -> Path:
    """Generate a high-quality 16:9 image using Animagine XL 3.1 or configured API."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # 1. Check for OpenAI DALL-E if key provided
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            logger.info("Attempting generation via OpenAI DALL-E 3 API...")
            headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
            payload = {
                "model": "dall-e-3",
                "prompt": prompt[:1000],
                "size": "1792x1024",
                "quality": "standard",
                "n": 1,
            }
            res = requests.post("https://api.openai.com/v1/images/generations", headers=headers, json=payload, timeout=90)
            if res.status_code == 200:
                img_url = res.json()["data"][0]["url"]
                img_data = requests.get(img_url, timeout=60).content
                out_path.write_bytes(img_data)
                _ensure_1080p(out_path)
                logger.info(f"✔ DALL-E 3 generated image in {time.time()-t0:.2f}s -> {out_path.resolve()}")
                return out_path
        except Exception as e:
            logger.warning(f"OpenAI generation failed: {e}")

    # 2. Check for Cloudflare Workers AI if configured
    cf_acc = os.environ.get("CF_ACCOUNT_ID")
    cf_tok = os.environ.get("CF_API_TOKEN")
    if cf_acc and cf_tok:
        try:
            logger.info("Attempting generation via Cloudflare Workers AI (Flux Schnell)...")
            url = f"https://api.cloudflare.com/client/v4/accounts/{cf_acc}/ai/run/@cf/black-forest-labs/flux-1-schnell"
            headers = {"Authorization": f"Bearer {cf_tok}"}
            res = requests.post(url, headers=headers, json={"prompt": prompt[:500], "steps": 6}, timeout=90)
            if res.status_code == 200:
                ct = res.headers.get("content-type", "").lower()
                if ct.startswith("image/"):
                    out_path.write_bytes(res.content)
                    _ensure_1080p(out_path)
                    logger.info(f"✔ Cloudflare Flux generated image in {time.time()-t0:.2f}s -> {out_path.resolve()}")
                    return out_path
                elif ct.startswith("application/json"):
                    b64 = res.json().get("result", {}).get("image")
                    if b64:
                        if b64.startswith("data:image"):
                            b64 = b64.split(",", 1)[1]
                        out_path.write_bytes(base64.b64decode(b64))
                        _ensure_1080p(out_path)
                        logger.info(f"✔ Cloudflare Flux generated image in {time.time()-t0:.2f}s -> {out_path.resolve()}")
                        return out_path
        except Exception as e:
            logger.warning(f"Cloudflare generation failed: {e}")

    # 3. High-Quality Animagine XL 3.1 Space (supports full anime styling, sexy/nsfw outfits)
    client = get_animagine_client()
    if client is not None:
        logger.info(f"Dispatching prompt to Animagine XL 3.1 Space (seed={seed}, size=1344x768)...")
        for attempt in range(1, 4):
            try:
                res = client.predict(
                    prompt[:500],
                    negative_prompt,
                    seed,
                    1344,
                    768,
                    7.0,
                    20,
                    'Euler a',
                    '1344 x 768',
                    'Anime',
                    'Standard v3.1',
                    False,
                    0.5,
                    1.2,
                    True,
                    api_name='/run'
                )
                if res and isinstance(res, (tuple, list)) and len(res) > 0 and len(res[0]) > 0:
                    img_item = res[0][0]
                    temp_p = None
                    if isinstance(img_item, dict):
                        temp_p = img_item.get("image") or img_item.get("path") or img_item.get("name")
                    elif isinstance(img_item, str):
                        temp_p = img_item
                    elif isinstance(img_item, (tuple, list)) and len(img_item) > 0:
                        temp_p = img_item[0]

                    if temp_p and Path(temp_p).exists():
                        shutil.copy(temp_p, out_path)
                        _ensure_1080p(out_path)
                        logger.info(f"✔ Animagine XL 3.1 generated image in {time.time()-t0:.2f}s -> {out_path.resolve()}")
                        return out_path
                    else:
                        logger.warning(f"Extracted image path '{temp_p}' not found or invalid from res: {res}")
            except Exception as e:
                err_msg = str(e)
                if "ZeroGPU quota" in err_msg:
                    logger.warning(
                        "ZeroGPU quota reached on free tier. Browser sessions queue interactively; "
                        "API calls require remaining daily allocation. Falling back to keyframe render."
                    )
                    _create_cinematic_fallback(prompt, out_path)
                    return out_path
                logger.warning(f"Animagine XL attempt {attempt}/3 error: {err_msg}. Waiting 2s before retry...")
                time.sleep(2)

    # 4. Fallback safeguard
    logger.info("Using visual cinematic backdrop safeguard.")
    _create_cinematic_fallback(prompt, out_path)
    return out_path


def _ensure_1080p(path: Path):
    """Resize image cleanly to 1920x1080 with Lanczos filter."""
    try:
        with Image.open(path) as img:
            if img.size != (VIDEO_WIDTH, VIDEO_HEIGHT):
                resized = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.Resampling.LANCZOS)
                resized.save(path, format="JPEG", quality=95)
    except Exception:
        pass
