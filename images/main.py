from __future__ import annotations
import sys
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from logger import setup_logger, log_step
from images.generator import generate_single_image


def main():
    out_dir = ROOT_DIR / "images" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_file = out_dir / "execution.log"
    logger = setup_logger("images", log_file=log_file)

    parser = argparse.ArgumentParser(description="Standalone High-Quality Anime Image Generator")
    parser.add_argument("prompt", nargs="?", help="Image prompt (e.g. 'hatsune miku in sexy outfit')")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for consistency")
    parser.add_argument("--out", help="Custom output image file path")
    args = parser.parse_args()

    prompt = args.prompt
    if not prompt:
        prompt = input("Enter image prompt: ").strip()
        if not prompt:
            prompt = "1girl, hatsune miku, aqua eyes, teal twintails, sexy stylish outfit, 16:9, masterpiece, best quality"

    out_file = Path(args.out) if args.out else (out_dir / f"img_{ts}.jpg")

    with log_step(logger, f"Generating image for prompt: \"{prompt[:60]}...\""):
        logger.info(f"Target file: {out_file.resolve()}")
        logger.info(f"Random seed: {args.seed}")
        saved_path = generate_single_image(prompt, out_file, seed=args.seed)

        size_kb = out_file.stat().st_size / 1024
        logger.info("==================== IMAGE CREATED ====================")
        logger.info(f"✨ File:       {saved_path.resolve()}")
        logger.info(f"📐 Resolution: 1920x1080 (16:9 widescreen)")
        logger.info(f"📦 File Size:  {size_kb:.1f} KB")
        logger.info(f"📝 Log File:   {log_file.resolve()}")
        logger.info("=======================================================")


if __name__ == "__main__":
    main()
