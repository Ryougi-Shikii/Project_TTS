from __future__ import annotations
import asyncio
import shutil
import subprocess
from pathlib import Path
from pydantic import BaseModel
import edge_tts

VOICE_CATALOG = {
    "female_teen": ["en-US-AnaNeural", "en-US-JennyNeural"],
    "female_adult": ["en-US-AriaNeural", "en-US-AvaNeural"],
    "male_teen": ["en-US-GuyNeural", "en-US-BrianNeural"],
    "male_adult": ["en-US-ChristopherNeural", "en-US-AndrewNeural", "en-US-EricNeural"],
    "narrator": ["en-US-GuyNeural"]
}


class VoiceClip(BaseModel):
    line_id: str
    speaker: str
    text: str
    path: str
    duration_ms: int


def _probe_duration_ms(path: Path) -> int:
    """Accurately probe audio file duration using ffprobe."""
    if not shutil.which("ffprobe") or not path.exists():
        return 2000
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ], text=True).strip()
        return max(500, int(float(out) * 1000))
    except Exception:
        return 2000


def assign_voices_dynamically(characters: list) -> dict[str, dict]:
    """Dynamically assign distinct voices to each character in the scene."""
    voice_map = {}
    used_voices = set()

    for char in characters:
        gender = getattr(char, "gender", "female").lower()
        age = getattr(char, "age_archetype", "young_adult").lower()

        if "female" in gender:
            pool = VOICE_CATALOG["female_teen"] if ("teen" in age or "young" in age) else VOICE_CATALOG["female_adult"]
        else:
            pool = VOICE_CATALOG["male_teen"] if ("teen" in age or "young" in age) else VOICE_CATALOG["male_adult"]

        picked = next((v for v in pool if v not in used_voices), pool[0])
        used_voices.add(picked)

        voice_map[char.name.lower()] = {
            "voice": picked,
            "color": getattr(char, "theme_color", "#00d2ff")
        }

    return voice_map


async def synthesize_line(
    line_id: str,
    speaker: str,
    text: str,
    voice: str,
    out_path: Path,
) -> VoiceClip:
    """Synthesize one line of dialogue with the assigned character voice."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    comm = edge_tts.Communicate(
        text=text,
        voice=voice,
    )
    await comm.save(str(out_path))

    duration_ms = _probe_duration_ms(out_path)
    return VoiceClip(
        line_id=line_id,
        speaker=speaker,
        text=text,
        path=str(out_path),
        duration_ms=duration_ms,
    )


async def synthesize_all(lines: list, characters: list, out_dir: Path) -> tuple[list[VoiceClip], dict]:
    """Dynamically cast voices and synthesize all lines concurrently."""
    voice_map = assign_voices_dynamically(characters)

    tasks = [
        synthesize_line(
            line.id,
            line.speaker,
            line.text,
            voice_map.get(line.speaker.lower(), {}).get("voice", "en-US-GuyNeural"),
            out_dir / f"{line.id}.mp3"
        )
        for line in lines
    ]
    clips = await asyncio.gather(*tasks)
    return list(clips), voice_map
