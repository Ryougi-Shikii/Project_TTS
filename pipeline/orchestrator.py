from __future__ import annotations
import re
import sys
import time
import asyncio
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from logger import setup_logger, log_step
from script.generator import generate_script, VideoScript
from voice.synthesizer import synthesize_all, VoiceClip
from images.generator import generate_single_image
from video.compositor import render_line_clip, stitch_video_clips


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", slug)[:24]


def _build_frame_prompt(script: VideoScript, line, char_spec) -> str:
    """Build a comprehensive cinematic prompt combining dynamic style, setting, and character visual DNA."""
    style = getattr(script, "art_style", "Cinematic anime, Makoto Shinkai aesthetic, 16:9 widescreen")
    setting = getattr(script, "setting", "atmospheric scene")
    char_dna = getattr(char_spec, "visual_dna", "detailed anime character")
    camera = getattr(line, "camera_shot", "medium shot")
    action = getattr(line, "visual_action", "looking forward")

    prompt = (
        f"{char_dna}, {setting}, "
        f"shot: {camera}, "
        f"action: {action}, "
        f"{style}, masterpiece, best quality, vibrant colors, 16:9 widescreen"
    )
    return prompt


async def run_pipeline(topic: str, custom_name: str | None = None) -> Path:
    """Run the complete end-to-end video production pipeline for ANY topic."""
    slug = custom_name or _slugify(topic) or "scene"
    ts = time.strftime("%Y%m%d_%H%M%S")
    session_dir = ROOT_DIR / "output" / f"{slug}_{ts}"
    session_dir.mkdir(parents=True, exist_ok=True)

    log_file = session_dir / "pipeline.log"
    logger = setup_logger("pipeline", log_file=log_file)

    logger.info("==================== PIPELINE START ====================")
    logger.info(f"🎬 Scene Topic:    \"{topic}\"")
    logger.info(f"📂 Output Folder:  {session_dir.resolve()}")
    logger.info(f"📝 Pipeline Log:   {log_file.resolve()}")
    logger.info("========================================================")

    # 1. SCRIPT
    with log_step(logger, "[1/4] Screenplay & Character Visual Sheets"):
        script: VideoScript = await generate_script(topic)
        script_file = session_dir / "script.json"
        script_file.write_text(script.model_dump_json(indent=2), encoding="utf-8")

        logger.info(f"Title:     \"{script.title}\"")
        logger.info(f"Art Style: {script.art_style}")
        logger.info(f"Setting:   {script.setting}")
        logger.info(f"Characters ({len(script.characters)}):")
        char_lookup = {c.name.lower(): c for c in script.characters}
        for c in script.characters:
            logger.info(f"  • {c.name.ljust(15)} ({c.gender}, {c.age_archetype}) -> DNA: {c.visual_dna[:65]}...")

        logger.info(f"Lines ({len(script.lines)}):")
        for l in script.lines:
            logger.info(f"  [{l.id}] {l.speaker.ljust(15)} ({l.emotion}): \"{l.text}\"")

    # 2. VOICE
    with log_step(logger, "[2/4] Multi-Character Voice Synthesis"):
        audio_dir = session_dir / "audio"
        audio_clips, voice_map = await synthesize_all(script.lines, script.characters, audio_dir)
        total_audio_ms = sum(c.duration_ms for c in audio_clips)
        for spk, vinfo in voice_map.items():
            logger.info(f"  • {spk.capitalize().ljust(15)} -> Voice: {vinfo['voice']}")
        for c in audio_clips:
            logger.info(f"  [{c.line_id}] {c.speaker.ljust(15)} ({c.duration_ms}ms) -> {Path(c.path).name}")

    # 3. IMAGES (Animagine XL 3.1)
    with log_step(logger, "[3/4] 16:9 Character-Consistent Diffusion"):
        images_dir = session_dir / "images"
        image_paths: list[Path] = []

        for idx, line in enumerate(script.lines):
            char_spec = char_lookup.get(line.speaker.lower(), script.characters[0])
            prompt = _build_frame_prompt(script, line, char_spec)
            img_out = images_dir / f"{line.id}.jpg"
            logger.info(f"  [~] Rendering frame {idx+1}/{len(script.lines)} [{line.id}] for {line.speaker}...")
            img_p = generate_single_image(prompt, img_out, seed=42 + idx)
            image_paths.append(img_p)
            size_kb = img_p.stat().st_size / 1024
            logger.info(f"  [✔] Frame {line.id} saved: {img_p.name} ({size_kb:.1f} KB)")

    # 4. VIDEO (Ken Burns motion + subtitles)
    with log_step(logger, "[4/4] Video Compositing & Shot Stitching"):
        segments_dir = session_dir / "segments"
        segment_paths: list[Path] = []

        for idx, (line, clip, img_p) in enumerate(zip(script.lines, audio_clips, image_paths)):
            char_spec = char_lookup.get(line.speaker.lower(), script.characters[0])
            seg_p = segments_dir / f"seg_{line.id}.mp4"
            logger.info(f"  Compositing shot {idx+1}/{len(script.lines)} [{line.id}] ({clip.duration_ms}ms)...")
            render_line_clip(
                image_path=img_p,
                audio_path=Path(clip.path),
                duration_ms=clip.duration_ms,
                line=line,
                char_spec=char_spec,
                out_path=seg_p,
                index=idx,
            )
            segment_paths.append(seg_p)

        final_video = session_dir / "final_video.mp4"
        logger.info(f"  Concatenating {len(segment_paths)} shots into master video...")
        stitch_video_clips(segment_paths, final_video)

    total_sec = (total_audio_ms / 1000.0) + (len(script.lines) * 0.35)
    video_size_mb = final_video.stat().st_size / (1024 * 1024)
    logger.info("==================== PIPELINE COMPLETE ====================")
    logger.info(f"✨ Master Video: {final_video.resolve()}")
    logger.info(f"⏱️ Duration:     ~{total_sec:.1f}s")
    logger.info(f"📐 Resolution:   1920x1080 (16:9, 25 FPS)")
    logger.info(f"🔊 Audio:        Stereo 44.1kHz AAC 192k")
    logger.info(f"📦 File Size:    {video_size_mb:.2f} MB")
    logger.info(f"📂 Folder:       {session_dir.resolve()}")
    logger.info("===========================================================")

    return final_video
