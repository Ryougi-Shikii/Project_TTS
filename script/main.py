from __future__ import annotations
import sys
import json
import time
import asyncio
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from logger import setup_logger, log_step
from script.generator import generate_script, VideoScript


def main():
    out_dir = ROOT_DIR / "script" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_file = out_dir / "execution.log"
    logger = setup_logger("script", log_file=log_file)

    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = input("Enter scene query (e.g. 'two detectives arguing in the rain'): ").strip()
        if not topic:
            topic = "Two cyberpunk hackers breaking into a server room"

    logger.info(f"Target query: \"{topic}\"")
    script: VideoScript = asyncio.run(generate_script(topic))

    out_file = out_dir / f"script_{ts}.json"
    out_file.write_text(script.model_dump_json(indent=2), encoding="utf-8")

    logger.info("==================== SCENE OVERVIEW ====================")
    logger.info(f"🎬 Title:     {script.title}")
    logger.info(f"🎨 Art Style: {script.art_style}")
    logger.info(f"🌆 Setting:   {script.setting}")
    logger.info(f"👥 Characters ({len(script.characters)}):")
    for c in script.characters:
        logger.info(f"   • {c.name.ljust(15)} ({c.gender}, {c.age_archetype}) -> DNA: {c.visual_dna[:65]}...")
    logger.info(f"📜 Dialogue Lines ({len(script.lines)}):")
    for l in script.lines:
        logger.info(f"   [{l.id}] {l.speaker.ljust(15)} ({l.emotion}): \"{l.text}\"")
    logger.info(f"💾 Saved script JSON to: {out_file.resolve()}")
    logger.info(f"📝 Execution log saved to: {log_file.resolve()}")
    logger.info("========================================================")


if __name__ == "__main__":
    main()
