from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class Pause(BaseModel):
    after_word: str
    ms: int = Field(..., ge=0, le=5000)


class SpeechLine(BaseModel):
    id: str
    speaker: str
    text: str
    emotion: str = "neutral"
    intensity: float = Field(0.5, ge=0.0, le=1.0)
    rate: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(0.0, ge=-50.0, le=50.0)
    volume: float = Field(0.0, ge=-50.0, le=50.0)
    pauses: list[Pause] = Field(default_factory=list)
    emphasis: list[str] = Field(default_factory=list)
    visual_cue: Optional[str] = None


class Script(BaseModel):
    title: str
    style: str
    language: str = "en"
    lines: list[SpeechLine]

    @field_validator("lines")
    @classmethod
    def _unique_ids(cls, lines: list[SpeechLine]) -> list[SpeechLine]:
        ids = [l.id for l in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("SpeechLine ids must be unique")
        return lines


class SpeakerVoice(BaseModel):
    speaker: str
    family: str = Field(..., description="Family name from list_voice_families")
    rationale: str = Field(..., description="One concrete sentence")


class VoiceCast(BaseModel):
    assignments: list[SpeakerVoice]

    def as_lookup(self) -> dict[str, str]:
        return {a.speaker.lower(): a.family for a in self.assignments}


class ScriptResult(BaseModel):
    script: Script
    story_toml: str = Field(
        ...,
        description=(
            "A complete TOML document with title, description, and brief. "
            "Must be parseable by tomllib.loads(). Do NOT include a [voices] block."
        ),
    )


class WordTiming(BaseModel):
    word: str
    start_ms: int
    end_ms: int


class AudioClip(BaseModel):
    line_id: str
    speaker: str
    text: str
    path: str
    voice: str
    provider: str
    duration_ms: int
    format: str = "wav"
    word_timings: list[WordTiming] = Field(default_factory=list)


class AudioBundle(BaseModel):
    title: str
    clips: list[AudioClip]
    total_duration_ms: int
    combined_path: Optional[str] = None