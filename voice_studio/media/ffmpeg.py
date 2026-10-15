from __future__ import annotations
import shutil
import subprocess
from pathlib import Path


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def run_ffmpeg(args: list[str]) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
    )


def silence_ms(ms: int, out_path: Path) -> Path:
    run_ffmpeg([
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", f"{ms / 1000:.3f}", str(out_path),
    ])
    return out_path


def concat_audio(clip_paths: list[Path], out_path: Path,
                 gap_path: Path | None = None) -> Path:
    """Concatenate clips into one file, re-encoding for format safety."""
    if not clip_paths:
        raise ValueError("no clips to concat")
    if len(clip_paths) == 1 and gap_path is None:
        shutil.copy(clip_paths[0], out_path)
        return out_path

    list_file = out_path.with_suffix(".concat.txt")
    entries: list[str] = []
    for i, p in enumerate(clip_paths):
        entries.append(f"file '{p.resolve().as_posix()}'")
        if gap_path is not None and i < len(clip_paths) - 1:
            entries.append(f"file '{gap_path.resolve().as_posix()}'")

    list_file.write_text("\n".join(entries), encoding="utf-8")
    run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:a", "libmp3lame", "-q:a", "2", str(out_path),
    ])
    list_file.unlink(missing_ok=True)
    return out_path


# ---- reserved for the video stage ----
def mux(video_path: Path, audio_path: Path, out_path: Path) -> Path:
    run_ffmpeg([
        "-i", str(video_path), "-i", str(audio_path),
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path),
    ])
    return out_path