from __future__ import annotations
import shutil
import subprocess
from pathlib import Path


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _run(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-nostdin", "-y", *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed:\n" + result.stderr.decode(errors="replace")
        )


def silence_ms(ms: int, out_path: Path) -> Path:
    _run([
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", f"{ms / 1000:.3f}", str(out_path),
    ])
    return out_path


def normalize_clip(src: Path, out: Path) -> Path:
    """Re-encode any audio file into a canonical mono 24 kHz s16le WAV.
    Fixes malformed PCM packets before they reach the concat demuxer."""
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "-i", str(src),
        "-ar", "24000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        "-fflags", "+genpts",
        str(out),
    ])
    return out


def concat_audio(clips: list[Path], out_path: Path,
                 gap_path: Path | None = None) -> Path:
    if not clips:
        raise ValueError("no clips to concat")
    if len(clips) == 1 and gap_path is None:
        shutil.copy(clips[0], out_path)
        return out_path

    work = out_path.parent / "_normalized"
    work.mkdir(parents=True, exist_ok=True)
    normalized: list[Path] = []
    for c in clips:
        dst = work / f"{c.stem}.wav"
        normalized.append(normalize_clip(c, dst))

    gap_wav = None
    if gap_path is not None:
        gap_wav = work / "_gap.wav"
        normalize_clip(gap_path, gap_wav)

    list_file = out_path.with_suffix(".concat.txt")
    entries: list[str] = []
    for i, p in enumerate(normalized):
        entries.append(f"file '{p.resolve().as_posix()}'")
        if gap_wav is not None and i < len(normalized) - 1:
            entries.append(f"file '{gap_wav.resolve().as_posix()}'")
    list_file.write_text("\n".join(entries), encoding="utf-8")

    _run([
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:a", "libmp3lame", "-q:a", "2", str(out_path),
    ])
    list_file.unlink(missing_ok=True)
    shutil.rmtree(work, ignore_errors=True)
    return out_path