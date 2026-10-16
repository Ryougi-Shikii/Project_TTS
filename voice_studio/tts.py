from __future__ import annotations
import asyncio
import importlib
import logging
import os
import time
import shutil
import subprocess
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, Optional

from voice_studio.config import TTS_CHAIN, VOICE_FAMILIES
from voice_studio.schemas import SpeechLine, AudioClip, WordTiming

log = logging.getLogger("voice_studio.tts")


# ═══════════════════════════════════════════════════════════════════════
# BASE
# ═══════════════════════════════════════════════════════════════════════

class TTSUnavailable(RuntimeError):
    """Missing key, SDK, or binary — the registry skips this provider."""


class TTSProvider(ABC):
    name: str = "base"

    def __init__(self, default_voice: str, cast: dict[str, str] | None = None):
        self.default_voice = default_voice
        self.cast = cast or {}

    def _voice_for(self, speaker: str) -> str:
        family = self.cast.get(speaker.lower())
        if family:
            voice = VOICE_FAMILIES.get(family, {}).get("voices", {}).get(self.name)
            if voice:
                return voice
        return self.default_voice

    @abstractmethod
    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip: ...

    def capabilities(self) -> dict:
        return {
            "emotion": False, "pauses": False, "emphasis": False,
            "word_timings": False, "voice_cloning": False,
        }


# ═══════════════════════════════════════════════════════════════════════
# PROVIDERS
# ═══════════════════════════════════════════════════════════════════════

class DeepgramTTSProvider(TTSProvider):
    name = "deepgram"

    def __init__(
        self,
        model: str = "aura-asteria-en",
        default_voice: str | None = None,
        cast: dict[str, str] | None = None,
        api_key: str | None = None,
    ):
        super().__init__(default_voice or model, cast)
        try:
            from deepgram import DeepgramClient
        except ImportError as e:
            raise TTSUnavailable("deepgram-sdk not installed") from e
        key = api_key or os.getenv("DEEPGRAM_API_KEY")
        if not key:
            raise TTSUnavailable("DEEPGRAM_API_KEY not set")
        self._client = DeepgramClient(api_key=key)
        self.model = model

    @staticmethod
    def _extract_bytes(response) -> bytes:
        if hasattr(response, "stream"):
            return b"".join(response.stream)
        if hasattr(response, "content"):
            c = response.content
            return bytes(c) if isinstance(c, (bytes, bytearray)) else b"".join(c)
        if isinstance(response, (bytes, bytearray)):
            return bytes(response)
        if isinstance(response, Iterable):
            return b"".join(response)
        raise RuntimeError(f"deepgram: unexpected response type {type(response)}")

    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip:
        voice = self._voice_for(line.speaker)
        response = await asyncio.to_thread(
            self._client.speak.v1.audio.generate,
            text=line.text, model=voice, encoding="mp3",
        )
        audio_bytes = self._extract_bytes(response)
        out_path = out_path.with_suffix(".mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio_bytes)
        return AudioClip(
            line_id=line.id, speaker=line.speaker, text=line.text,
            path=str(out_path), voice=voice, provider=self.name,
            duration_ms=0, format="mp3",
        )


class OrpheusProvider(TTSProvider):
    name = "orpheus"

    _EMOTION_TAGS = {
        "amused": "<chuckle>", "laughing": "<laugh>", "sad": "<sigh>",
        "tired": "<yawn>", "surprised": "<gasp>", "annoyed": "<groan>",
        "sick": "<cough>", "giggling": "<giggle>",
    }

    def __init__(
        self,
        model: str = "canopylabs/orpheus-v1-english",
        default_voice: str = "autumn",
        cast: dict[str, str] | None = None,
        api_key: str | None = None,
    ):
        super().__init__(default_voice, cast)
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

    def _prepare_text(self, line: SpeechLine) -> str:
        text = line.text
        for word in line.emphasis:
            text = text.replace(word, word.upper())
        tag = self._EMOTION_TAGS.get(line.emotion.lower())
        return f"{tag} {text}" if tag else text

    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip:
        voice = self._voice_for(line.speaker)
        payload = self._prepare_text(line)
        response = await asyncio.to_thread(
            self._client.audio.speech.create,
            model=self.model, voice=voice, input=payload,
            response_format="wav",
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(response.read())
        return AudioClip(
            line_id=line.id, speaker=line.speaker, text=line.text,
            path=str(out_path), voice=voice, provider=self.name,
            duration_ms=0, format="wav",
        )


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
    return "Say the following " + (", ".join(bits) if bits else "in a natural tone") + ": "


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
        cast: dict[str, str] | None = None,
        api_key: str | None = None,
    ):
        super().__init__(default_voice, cast)
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
                model=self.model, contents=prompt,
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
            line_id=line.id, speaker=line.speaker, text=line.text,
            path=str(out_path), voice=voice, provider=self.name,
            duration_ms=duration, format="wav",
        )


class EdgeTTSProvider(TTSProvider):
    name = "edge"

    def __init__(
        self,
        default_voice: str = "en-US-GuyNeural",
        cast: dict[str, str] | None = None,
    ):
        super().__init__(default_voice, cast)
        try:
            import edge_tts
        except ImportError as e:
            raise TTSUnavailable("edge-tts not installed") from e
        self._edge_tts = edge_tts

    def capabilities(self) -> dict:
        return {"emotion": False, "pauses": True, "emphasis": False,
                "word_timings": True, "voice_cloning": False}

    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip:
        voice = self._voice_for(line.speaker)
        rate = f"{int(round((line.rate - 1.0) * 100)):+d}%"
        pitch = f"{int(round(line.pitch)):+d}Hz"
        volume = f"{int(round(line.volume)):+d}%"

        comm = self._edge_tts.Communicate(
            line.text, voice, rate=rate, pitch=pitch, volume=volume,
        )

        audio = bytearray()
        timings: list[WordTiming] = []
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] // 10_000
                end = (chunk["offset"] + chunk["duration"]) // 10_000
                timings.append(WordTiming(word=chunk["text"], start_ms=start, end_ms=end))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(bytes(audio))
        duration = timings[-1].end_ms if timings else 0
        return AudioClip(
            line_id=line.id, speaker=line.speaker, text=line.text,
            path=str(out_path), voice=voice, provider=self.name,
            duration_ms=duration, format="mp3",
            word_timings=timings,
        )


# ═══════════════════════════════════════════════════════════════════════
# REGISTRY — provider-agnostic. Reads TTS_CHAIN, loads classes by path.
# ═══════════════════════════════════════════════════════════════════════

def _load_class(dotted: str):
    module_path, _, cls_name = dotted.partition(":")
    if not cls_name:
        raise ValueError(f"bad class path {dotted!r}")
    return getattr(importlib.import_module(module_path), cls_name)


class TTSRegistry:
    def __init__(
        self,
        cast: dict[str, str] | None = None,
        chain: list[dict] | None = None,
    ):
        self.cast = cast or {}
        self._entries: list[tuple[dict, TTSProvider]] = []
        for spec in (chain if chain is not None else TTS_CHAIN):
            try:
                cls = _load_class(spec["class"])
                provider = cls(**spec.get("args", {}), cast=self.cast)
                self._entries.append((spec, provider))
            except TTSUnavailable as e:
                log.warning("tts %s unavailable: %s", spec["name"], e)
            except Exception as e:
                log.warning("tts %s failed to construct: %s", spec["name"], e)
        if not self._entries:
            raise RuntimeError("no TTS providers available")

    def provider_names(self) -> list[str]:
        return [spec["name"] for spec, _ in self._entries]

    async def synthesize(self, line: SpeechLine, out_dir: Path) -> AudioClip:
        t0 = time.perf_counter()
        last_err = None
        for spec, provider in self._entries:
            ext = spec.get("extension", "mp3")
            out_path = out_dir / f"{line.id}.{ext}"
            try:
                clip = await provider.synthesize(line, out_path)
                if clip.duration_ms == 0:
                    clip = clip.model_copy(update={
                        "duration_ms": _probe_duration_ms(Path(clip.path)),
                    })
                dt = time.perf_counter() - t0
                log.info("  tts %s  %s/%s  %.2fs  %dms",
                        line.id, clip.provider, clip.voice, dt, clip.duration_ms)
                return clip
            except Exception as e:
                last_err = e
                log.debug("  tts %s  %s failed: %s", line.id, spec["name"], e)
        raise RuntimeError(f"all TTS providers failed for {line.id}") from last_err


def _probe_duration_ms(path: Path) -> int:
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