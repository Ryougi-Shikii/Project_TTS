from __future__ import annotations
import subprocess
from pathlib import Path

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 25


def _clean_text_for_ffmpeg(text: str) -> str:
    """Escape text safely for ffmpeg drawtext filter."""
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\u2019")
    text = text.replace(":", "\\:")
    text = text.replace("%", "\\%")
    return text


def render_line_clip(
    image_path: Path,
    audio_path: Path,
    duration_ms: int,
    line,
    char_spec=None,
    out_path: Path = None,
    index: int = 0,
) -> Path:
    """Render a single animated clip with Ken Burns motion, loud stereo audio, and styled subtitles."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    duration_sec = (duration_ms / 1000.0) + 0.35
    total_frames = max(25, int(duration_sec * VIDEO_FPS))

    theme_color = getattr(char_spec, "theme_color", "#00d2ff") if char_spec else "#00d2ff"
    spk_color = theme_color.replace("#", "0x")

    speaker_name = getattr(line, "speaker", "SPEAKER").upper()
    line_text = getattr(line, "text", "")

    safe_speaker = _clean_text_for_ffmpeg(speaker_name)
    safe_dialogue = _clean_text_for_ffmpeg(f'"{line_text}"')

    # Alternating subtle camera movement (slow zoom-in vs slow pan)
    if index % 2 == 0:
        pan_filter = (
            f"zoompan=z='min(zoom+0.0006,1.06)':d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
        )
    else:
        pan_filter = (
            f"zoompan=z='1.05':d={total_frames}:"
            f"x='(iw-iw/zoom)*(in/{total_frames})':y='ih/2-(ih/zoom/2)':s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
        )

    font_path = "C\\:/Windows/Fonts/arial.ttf"

    vf = (
        f"{pan_filter},"
        f"drawbox=y=ih-180:color=black@0.70:width=iw:height=180:t=fill,"
        f"drawbox=y=ih-182:color={spk_color}:width=iw:height=4:t=fill,"
        f"drawtext=fontfile='{font_path}':text='{safe_speaker}':fontcolor={spk_color}:fontsize=30:x=80:y=h-150,"
        f"drawtext=fontfile='{font_path}':text='{safe_dialogue}':fontcolor=white:fontsize=36:x=80:y=h-100"
    )

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-af", "volume=1.8,aformat=channel_layouts=stereo:sample_rates=44100",
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-t", f"{duration_sec:.2f}",
        str(out_path)
    ]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg render failed:\n{res.stderr}")

    return out_path


def stitch_video_clips(clip_paths: list[Path], final_video_path: Path) -> Path:
    """Concatenate individual segment MP4s into the final video."""
    final_video_path.parent.mkdir(parents=True, exist_ok=True)

    concat_file = final_video_path.parent / "concat_list.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in clip_paths]
    concat_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        str(final_video_path)
    ]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    concat_file.unlink(missing_ok=True)

    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed:\n{res.stderr}")

    return final_video_path
