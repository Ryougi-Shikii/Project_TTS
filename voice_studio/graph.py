from __future__ import annotations
from pathlib import Path
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from voice_studio.config import INTER_LINE_PAUSE_MS
from voice_studio.schemas import Script, AudioBundle
from voice_studio.tts.registry import TTSRegistry
from voice_studio.voices import VoiceResolver
from voice_studio.agents.script_agent import write_script
from voice_studio.agents.audio_agent import produce_audio
from voice_studio.media import ffmpeg


class PipelineState(TypedDict, total=False):
    brief: str
    output_dir: str
    voice_overrides: dict[str, str]
    script: Optional[Script]
    audio: Optional[AudioBundle]
    errors: list[str]


async def node_write_script(state: PipelineState) -> PipelineState:
    return {"script": await write_script(state["brief"])}


async def node_produce_audio(state: PipelineState) -> PipelineState:
    script = state["script"]

    # Speakers are known now. Build a resolver with stable per-speaker slots.
    resolver = VoiceResolver(
        speakers=[l.speaker for l in script.lines],
        explicit=state.get("voice_overrides") or {},
    )
    registry = TTSRegistry(voice_resolver=resolver)

    out_dir = Path(state["output_dir"]) / "audio"
    bundle = await produce_audio(
        script=script, registry=registry, out_dir=out_dir,
    )
    return {"audio": bundle}


async def node_stitch(state: PipelineState) -> PipelineState:
    bundle = state["audio"]
    if not bundle or not ffmpeg.ffmpeg_available():
        return {}

    out_dir = Path(state["output_dir"]) / "audio"
    gap = out_dir / "_gap.mp3"
    ffmpeg.silence_ms(INTER_LINE_PAUSE_MS, gap)

    combined = out_dir / "full.mp3"
    ffmpeg.concat_audio(
        [Path(c.path) for c in bundle.clips],
        combined,
        gap_path=gap,
    )
    return {"audio": bundle.model_copy(update={"combined_path": str(combined)})}


def build_pipeline():
    g = StateGraph(PipelineState)
    g.add_node("write_script", node_write_script)
    g.add_node("produce_audio", node_produce_audio)
    g.add_node("stitch_audio", node_stitch)

    g.add_edge(START, "write_script")
    g.add_edge("write_script", "produce_audio")
    g.add_edge("produce_audio", "stitch_audio")
    g.add_edge("stitch_audio", END)
    return g.compile()


async def run_pipeline(
    brief: str,
    output_dir: str,
    *,
    voice_overrides: dict[str, str] | None = None,
) -> PipelineState:
    return await build_pipeline().ainvoke({
        "brief": brief,
        "output_dir": output_dir,
        "voice_overrides": voice_overrides or {},
    })