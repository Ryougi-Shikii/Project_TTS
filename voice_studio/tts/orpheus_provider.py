from __future__ import annotations
import asyncio
import os
from pathlib import Path

from voice_studio.schemas import SpeechLine, AudioClip
from voice_studio.tts.base import TTSProvider, TTSUnavailable

_EMOTION_TAGS = {
    "amused":    "<chuckle>",
    "laughing":  "<laugh>",
    "sad":       "<sigh>",
    "tired":     "<yawn>",
    "surprised": "<gasp>",
    "annoyed":   "<groan>",
    "sick":      "<cough>",
    "giggling":  "<giggle>",
}


def _prepare_text(line: SpeechLine) -> str:
    text = line.text
    for word in line.emphasis:
        text = text.replace(word, word.upper())
    tag = _EMOTION_TAGS.get(line.emotion.lower())
    if tag:
        text = f"{tag} {text}"
    return text


class OrpheusProvider(TTSProvider):
    name = "orpheus"

    def __init__(
        self,
        model: str = "canopylabs/orpheus-v1-english",
        default_voice: str = "autumn",
        voice_resolver=None,
        api_key: str | None = None,
    ):
        super().__init__(default_voice, voice_resolver)

        try:
            from groq import Groq
        except ImportError as e:
            raise TTSUnavailable("groq SDK not installed") from e

        key = api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise TTSUnavailable("GROQ_API_KEY not set")

        self._client = Groq(api_key=key)
        self.model = model

    def capabilities(self) -> dict:
        return {"emotion": True, "pauses": True, "emphasis": True,
                "word_timings": False, "voice_cloning": False}

    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip:
        voice = self._voice_for(line.speaker)
        payload = _prepare_text(line)

        response = await asyncio.to_thread(
            self._client.audio.speech.create,
            model=self.model,
            voice=voice,
            input=payload,
            response_format="wav",
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(response.read())

        return AudioClip(
            line_id=line.id,
            speaker=line.speaker,
            text=line.text,
            path=str(out_path),
            voice=voice,
            provider=self.name,
            duration_ms=0,
            format="wav",
            word_timings=[],
        )