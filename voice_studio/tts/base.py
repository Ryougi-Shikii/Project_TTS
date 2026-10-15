from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional

from voice_studio.schemas import SpeechLine, AudioClip

# (provider_name, speaker) -> voice, or None to fall back to default.
VoiceResolverFn = Callable[[str, str], Optional[str]]


class TTSProvider(ABC):
    """Every TTS backend implements this."""

    name: str = "base"

    def __init__(
        self,
        default_voice: str,
        voice_resolver: VoiceResolverFn | None = None,
    ):
        self.default_voice = default_voice
        self.voice_resolver = voice_resolver

    def _voice_for(self, speaker: str) -> str:
        if self.voice_resolver is not None:
            resolved = self.voice_resolver(self.name, speaker)
            if resolved:
                return resolved
        return self.default_voice

    @abstractmethod
    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip:
        ...

    def capabilities(self) -> dict:
        return {
            "emotion": False,
            "pauses": False,
            "emphasis": False,
            "word_timings": False,
            "voice_cloning": False,
        }


class TTSUnavailable(RuntimeError):
    """Missing key, missing SDK, missing binary — registry skips."""