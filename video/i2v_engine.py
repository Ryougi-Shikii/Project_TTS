from __future__ import annotations
import os
import shutil
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

try:
    from gradio_client import Client, handle_file
except ImportError:
    Client = None
    handle_file = None

ROOT_DIR = Path(__file__).resolve().parent.parent

_svd_client = None


def get_svd_client():
    """Connect to Stable Video Diffusion (SVD) Space on Hugging Face."""
    global _svd_client
    if _svd_client is None and Client is not None:
        token = os.environ.get("huggingface_colab") or os.environ.get("HF_TOKEN")
        try:
            if token:
                _svd_client = Client("mediasynthesismuseum/stable-video-diffusion", token=token)
            else:
                _svd_client = Client("mediasynthesismuseum/stable-video-diffusion")
        except Exception:
            _svd_client = None
    return _svd_client


def generate_ai_video(
    image_path: Path,
    out_path: Path,
    seed: int = 42,
    motion_bucket_id: int = 127,
    fps_id: int = 6,
) -> Path:
    """Generate an AI-driven Image-to-Video MP4 using Stable Video Diffusion via Gradio Space."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    client = get_svd_client()

    if client is None:
        raise RuntimeError("Could not connect to SVD video space. Make sure gradio_client is installed.")

    print(f"     [~] Sending image {image_path.name} to Stable Video Diffusion space...")
    try:
        res = client.predict(
            image=handle_file(str(image_path)),
            seed=seed,
            randomize_seed=True,
            motion_bucket_id=motion_bucket_id,
            fps_id=fps_id,
            api_name="/video"
        )
        if res and isinstance(res, (tuple, list)) and len(res) > 0:
            video_dict = res[0]
            if isinstance(video_dict, dict) and "video" in video_dict:
                temp_video = video_dict["video"]
                if Path(temp_video).exists():
                    shutil.copy(temp_video, out_path)
                    print(f"     [✓] AI Video generated: {out_path.name}")
                    return out_path
        raise RuntimeError(f"Unexpected response format from SVD space: {res}")
    except Exception as e:
        raise RuntimeError(f"SVD space video generation failed: {e}")
