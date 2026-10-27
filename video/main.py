from __future__ import annotations
import sys
import time
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from logger import setup_logger, log_step
from video.compositor import render_line_clip, stitch_video_clips


class SimpleLine:
    def __init__(self, speaker: str, text: str):
        self.speaker = speaker
        self.text = text


class SimpleChar:
    def __init__(self, color: str = "#00d2ff"):
        self.theme_color = color


def main():
    out_dir = ROOT_DIR / "video" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_file = out_dir / "execution.log"
    logger = setup_logger("video", log_file=log_file)

    parser = argparse.ArgumentParser(description="Standalone Video Compositor")
    parser.add_argument("--image", required=True, help="Path to input image file (.jpg/.png)")
    parser.add_argument("--audio", required=True, help="Path to input audio file (.mp3/.wav)")
    parser.add_argument("--speaker", default="SPEAKER", help="Character speaker name")
    parser.add_argument("--text", default="Spoken dialogue line", help="Dialogue subtitle text")
    parser.add_argument("--color", default="#00d2ff", help="Hex color for speaker nameplate")
    parser.add_argument("--duration-ms", type=int, default=3000, help="Duration in milliseconds if audio is silent")
    parser.add_argument("--engine", choices=["ken_burns", "ai_svd"], default="ken_burns", help="Motion engine (Ken Burns or SVD Space)")
    args = parser.parse_args()

    img_p = Path(args.image)
    aud_p = Path(args.audio)
    if not img_p.exists():
        logger.error(f"Image {img_p} not found.")
        return
    if not aud_p.exists():
        logger.error(f"Audio {aud_p} not found.")
        return

    out_file = out_dir / f"video_{ts}.mp4"

    if args.engine == "ai_svd":
        with log_step(logger, "Stable Video Diffusion AI Image-to-Video generation"):
            try:
                from video.i2v_engine import generate_ai_video
                ai_raw = out_dir / f"svd_raw_{ts}.mp4"
                generate_ai_video(img_p, ai_raw)
                logger.info(f"✔ AI Video generated: {ai_raw.name}")
            except Exception as e:
                logger.warning(f"SVD Space error: {e}. Falling back to Ken Burns cinematic motion.")

    with log_step(logger, "Rendering 1080p video clip with Ken Burns camera motion & subtitles"):
        line = SimpleLine(args.speaker, args.text)
        char = SimpleChar(args.color)

        render_line_clip(
            image_path=img_p,
            audio_path=aud_p,
            duration_ms=args.duration_ms,
            line=line,
            char_spec=char,
            out_path=out_file,
        )

        size_mb = out_file.stat().st_size / (1024 * 1024)
        logger.info("==================== VIDEO CREATED ====================")
        logger.info(f"✨ File:       {out_file.resolve()}")
        logger.info(f"📐 Resolution: 1920x1080 (16:9 widescreen, 25 FPS)")
        logger.info(f"🔊 Audio:      Stereo 44.1kHz AAC 192k")
        logger.info(f"📦 File Size:  {size_mb:.2f} MB")
        logger.info(f"📝 Log File:   {log_file.resolve()}")
        logger.info("=======================================================")


if __name__ == "__main__":
    main()
