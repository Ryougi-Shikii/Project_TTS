from __future__ import annotations
import asyncio
import os
import wave
from pathlib import Path

from voice_studio.schemas import SpeechLine, AudioClip
from voice_studio.tts.base import TTSProvider, TTSUnavailable


def _style_prefix(line: SpeechLine) -> str:
    bits = []
    if line.emotion and line.emotion != "neutral":
        bits.append(line.emotion)
    if line.intensity >= 0.75:
        bits.append("with strong intensity")
    elif line.intensity <= 0.25:
        bits.append("subdued")
    if line.rate < 0.9:
        bits.append("slowly")
    elif line.rate > 1.1:
        bits.append("quickly")
    style = ", ".join(bits) if bits else "in a natural tone"
    return f"Say the following {style}: "


def _pcm_to_wav(pcm: bytes, path: Path, rate: int = 24000, channels: int = 1) -> int:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return int(len(pcm) / (2 * channels) / rate * 1000)


class GeminiTTSProvider(TTSProvider):
    name = "gemini"

    def __init__(
        self,
        model: str = "gemini-2.5-flash-preview-tts",
        default_voice: str = "Kore",
        voice_resolver=None,
        api_key: str | None = None,
    ):
        super().__init__(default_voice, voice_resolver)

        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise TTSUnavailable("google-genai not installed") from e

        key = api_key or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise TTSUnavailable("GOOGLE_API_KEY not set")

        self._genai = genai
        self._types = types
        self._client = genai.Client(api_key=key)
        self.model = model

    def capabilities(self) -> dict:
        return {"emotion": True, "pauses": False, "emphasis": False,
                "word_timings": False, "voice_cloning": False}

    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip:
        voice = self._voice_for(line.speaker)
        prompt = _style_prefix(line) + line.text

        def _call():
            return self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=self._types.SpeechConfig(
                        voice_config=self._types.VoiceConfig(
                            prebuilt_voice_config=self._types.PrebuiltVoiceConfig(
                                voice_name=voice,
                            )
                        )
                    ),
                ),
            )

        response = await asyncio.to_thread(_call)
        pcm = response.candidates[0].content.parts[0].inline_data.data

        out_path = out_path.with_suffix(".wav")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        duration = _pcm_to_wav(pcm, out_path)

        return AudioClip(
            line_id=line.id,
            speaker=line.speaker,
            text=line.text,
            path=str(out_path),
            voice=voice,
            provider=self.name,
            duration_ms=duration,
            format="wav",
            word_timings=[],
        )