from __future__ import annotations
import importlib
import logging
from pathlib import Path

from voice_studio.config import TTS_CHAIN
from voice_studio.schemas import SpeechLine, AudioClip
from voice_studio.tts.base import TTSProvider, TTSUnavailable
from voice_studio.voices import VoiceResolver

log = logging.getLogger(__name__)


def _load_class(dotted: str):
    module_path, _, cls_name = dotted.partition(":")
    if not cls_name:
        raise ValueError(f"class path must be 'module:Class', got {dotted!r}")
    return getattr(importlib.import_module(module_path), cls_name)


class TTSRegistry:
    """Ordered chain of providers built entirely from config.TTS_CHAIN.
    Knows nothing about any specific provider."""

    def __init__(
        self,
        voice_resolver: VoiceResolver | None = None,
        chain: list[dict] | None = None,
    ):
        self._entries: list[tuple[dict, TTSProvider]] = []
        for spec in (chain if chain is not None else TTS_CHAIN):
            try:
                cls = _load_class(spec["class"])
                provider = cls(
                    **spec.get("args", {}),
                    voice_resolver=voice_resolver,
                )
                self._entries.append((spec, provider))
            except TTSUnavailable as e:
                log.warning("tts %s unavailable: %s", spec["name"], e)
            except Exception as e:
                log.warning("tts %s failed to construct: %s", spec["name"], e)
        if not self._entries:
            raise RuntimeError("no TTS providers available")

    async def synthesize(self, line: SpeechLine, out_dir: Path) -> AudioClip:
        last_err: Exception | None = None
        for spec, provider in self._entries:
            ext = spec.get("extension", "mp3")
            out_path = out_dir / f"{line.id}.{ext}"
            try:
                clip = await provider.synthesize(line, out_path)
                if clip.duration_ms == 0:
                    clip = clip.model_copy(update={
                        "duration_ms": _probe_duration_ms(Path(clip.path))
                    })
                return clip
            except Exception as e:
                last_err = e
                log.warning("tts %s failed on %s: %s", spec["name"], line.id, e)
        raise RuntimeError(f"all TTS providers failed for {line.id}") from last_err


def _probe_duration_ms(path: Path) -> int:
    import shutil, subprocess
    if not shutil.which("ffprobe") or not path.exists():
        return 0
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ], text=True).strip()
        return int(float(out) * 1000)
    except Exception:
        return 0