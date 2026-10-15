from __future__ import annotations
from pathlib import Path

import edge_tts

from voice_studio.schemas import SpeechLine, AudioClip, WordTiming
from voice_studio.tts.base import TTSProvider, TTSUnavailable


def _pct(v: float) -> str:
    return f"{int(round(v)):+d}%"


def _hz(v: float) -> str:
    return f"{int(round(v)):+d}Hz"


class EdgeTTSProvider(TTSProvider):
    name = "edge"

    def __init__(
        self,
        default_voice: str = "en-US-GuyNeural",
        voice_resolver=None,
    ):
        super().__init__(default_voice, voice_resolver)
        if edge_tts is None:
            raise TTSUnavailable("edge-tts is not installed")

    def capabilities(self) -> dict:
        return {"emotion": False, "pauses": True, "emphasis": False,
                "word_timings": True, "voice_cloning": False}

    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip:
        voice = self._voice_for(line.speaker)
        rate = _pct((line.rate - 1.0) * 100)
        pitch = _hz(line.pitch)
        volume = _pct(line.volume)

        comm = edge_tts.Communicate(
            line.text, voice, rate=rate, pitch=pitch, volume=volume
        )

        audio = bytearray()
        timings: list[WordTiming] = []

        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] // 10_000
                end = (chunk["offset"] + chunk["duration"]) // 10_000
                timings.append(WordTiming(
                    word=chunk["text"], start_ms=start, end_ms=end))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(bytes(audio))

        duration = timings[-1].end_ms if timings else 0
        return AudioClip(
            line_id=line.id,
            speaker=line.speaker,
            text=line.text,
            path=str(out_path),
            voice=voice,
            provider=self.name,
            duration_ms=duration,
            format="mp3",
            word_timings=timings,
        )