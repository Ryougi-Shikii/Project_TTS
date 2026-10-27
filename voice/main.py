from __future__ import annotations
import sys
import json
import time
import argparse
import asyncio
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from logger import setup_logger, log_step
from voice.synthesizer import synthesize_line, synthesize_all, assign_voices_dynamically


def main():
    out_dir = ROOT_DIR / "voice" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_file = out_dir / "execution.log"
    logger = setup_logger("voice", log_file=log_file)

    parser = argparse.ArgumentParser(description="Standalone Voice Synthesizer")
    parser.add_argument("text", nargs="?", help="Text to speak (if single line)")
    parser.add_argument("--speaker", default="Speaker", help="Speaker name")
    parser.add_argument("--gender", default="female", choices=["female", "male"])
    parser.add_argument("--voice", default="en-US-AnaNeural", help="Specific Edge TTS voice")
    parser.add_argument("--script", help="Path to a script.json to synthesize all lines")
    args = parser.parse_args()

    if args.script:
        p = Path(args.script)
        if not p.exists():
            logger.error(f"Script file {p} does not exist.")
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        from script.generator import VideoScript
        script = VideoScript.model_validate(data)
        session_out = out_dir / f"session_{ts}"
        
        with log_step(logger, f"Batch synthesizing {len(script.lines)} dialogue lines from {p.name}"):
            clips, vmap = asyncio.run(synthesize_all(script.lines, script.characters, session_out))
            logger.info("==================== VOICE CASTING ====================")
            for spk, vinfo in vmap.items():
                logger.info(f"   • {spk.capitalize().ljust(15)} -> Voice: {vinfo['voice']}")
            logger.info("==================== AUDIO CLIPS ======================")
            for c in clips:
                logger.info(f"   [{c.line_id}] {c.speaker.ljust(15)} ({c.duration_ms}ms) -> {c.path}")
            logger.info(f"📂 Audio output directory: {session_out.resolve()}")
            logger.info(f"📝 Execution log saved to: {log_file.resolve()}")
            logger.info("=======================================================")
    else:
        text = args.text or "Ready whenever you are. Let's make something amazing!"
        out_file = out_dir / f"voice_{ts}.mp3"
        with log_step(logger, f"Synthesizing single line with {args.voice}"):
            clip = asyncio.run(synthesize_line("solo", args.speaker, text, args.voice, out_file))
            logger.info(f"✔ Audio saved: {out_file.resolve()} (duration: {clip.duration_ms}ms, voice: {args.voice})")
            logger.info(f"📝 Execution log saved to: {log_file.resolve()}")


if __name__ == "__main__":
    main()
