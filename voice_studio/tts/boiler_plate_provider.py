from __future__ import annotations
import asyncio
import os
from pathlib import Path

from voice_studio.schemas import SpeechLine, AudioClip
from voice_studio.tts.base import TTSProvider, TTSUnavailable


class OpenAITTSProvider(TTSProvider):
    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini-tts",
        default_voice: str = "alloy",
        voice_resolver=None,
        api_key: str | None = None,
    ):
        super().__init__(default_voice, voice_resolver)

        try:
            from openai import OpenAI
        except ImportError as e:
            raise TTSUnavailable("openai SDK not installed") from e

        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise TTSUnavailable("OPENAI_API_KEY not set")

        self._client = OpenAI(api_key=key)
        self.model = model

    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip:
        voice = self._voice_for(line.speaker)

        response = await asyncio.to_thread(
            self._client.audio.speech.create,
            model=self.model,
            voice=voice,
            input=line.text,
            response_format="mp3",
        )

        out_path = out_path.with_suffix(".mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(response.content)

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