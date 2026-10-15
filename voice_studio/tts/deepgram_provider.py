from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
from typing import Iterable

from voice_studio.schemas import SpeechLine, AudioClip
from voice_studio.tts.base import TTSProvider, TTSUnavailable

log = logging.getLogger(__name__)


def _extract_bytes(response) -> bytes:
    if hasattr(response, "stream"):
        log.debug("deepgram: using response.stream")
        return b"".join(response.stream)
    if hasattr(response, "content"):
        log.debug("deepgram: using response.content")
        content = response.content
        if isinstance(content, (bytes, bytearray)):
            return bytes(content)
        return b"".join(content)
    if isinstance(response, (bytes, bytearray)):
        log.debug("deepgram: response is raw bytes")
        return bytes(response)
    if isinstance(response, Iterable):
        log.debug("deepgram: response is iterable")
        return b"".join(response)
    raise RuntimeError(f"deepgram: cannot extract bytes from {type(response)}")


class DeepgramTTSProvider(TTSProvider):
    name = "deepgram"

    def __init__(
        self,
        model: str = "aura-asteria-en",
        default_voice: str | None = None,
        voice_resolver=None,
        api_key: str | None = None,
    ):
        # In Aura, "voice" IS the model name.
        super().__init__(default_voice or model, voice_resolver)

        try:
            from deepgram import DeepgramClient
        except ImportError as e:
            raise TTSUnavailable("deepgram-sdk not installed") from e

        key = api_key or os.getenv("DEEPGRAM_API_KEY")
        if not key:
            raise TTSUnavailable("DEEPGRAM_API_KEY not set")

        self._client = DeepgramClient(api_key=key)
        self.model = model

    def capabilities(self) -> dict:
        return {"emotion": False, "pauses": False, "emphasis": False,
                "word_timings": False, "voice_cloning": False}

    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip:
        voice = self._voice_for(line.speaker)

        def _call():
            return self._client.speak.v1.audio.generate(
                text=line.text, model=voice, encoding="mp3",
            )

        response = await asyncio.to_thread(_call)
        audio_bytes = _extract_bytes(response)

        out_path = out_path.with_suffix(".mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio_bytes)

        return AudioClip(
            line_id=line.id,
            speaker=line.speaker,
            text=line.text,
            path=str(out_path),
            voice=voice,
            provider=self.name,
            duration_ms=0,
            format="mp3",
            word_timings=[],
        )