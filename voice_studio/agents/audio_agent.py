from __future__ import annotations
import json
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware, ToolRetryMiddleware
from langchain.tools import tool

from voice_studio.config import build_model
from voice_studio.schemas import Script, AudioBundle, AudioClip
from voice_studio.tts.registry import TTSRegistry
from voice_studio.agents.prompts import AUDIO_PROMPT


def _make_synth_tool(script: Script, registry: TTSRegistry, out_dir: Path):
    by_id = {l.id: l for l in script.lines}
    done: dict[str, AudioClip] = {}

    @tool
    async def synthesize_speech(line_id: str) -> str:
        """Synthesize audio for one script line. Pass the line's `id`."""
        line = by_id.get(line_id)
        if line is None:
            return json.dumps({"error": f"unknown line_id '{line_id}'"})
        if line_id in done:
            return done[line_id].model_dump_json()
        clip = await registry.synthesize(line, out_dir)
        done[line_id] = clip
        return clip.model_dump_json()

    return synthesize_speech, done


async def produce_audio(
    script: Script,
    registry: TTSRegistry,
    out_dir: Path,
    *,
    fill_missing: bool = True,
) -> AudioBundle:
    out_dir.mkdir(parents=True, exist_ok=True)
    synth_tool, done = _make_synth_tool(script, registry, out_dir)

    agent = create_agent(
        model=build_model("director"),
        tools=[synth_tool],
        system_prompt=AUDIO_PROMPT,
        middleware=[
            ModelRetryMiddleware(max_retries=3),
            ToolRetryMiddleware(max_retries=2),
        ],
    )

    await agent.ainvoke({
        "messages": [{
            "role": "user",
            "content": f"Produce audio for this script:\n\n{script.model_dump_json(indent=2)}",
        }]
    })

    if fill_missing:
        for line in script.lines:
            if line.id not in done:
                done[line.id] = await registry.synthesize(line, out_dir)

    clips = [done[l.id] for l in script.lines if l.id in done]
    return AudioBundle(
        title=script.title,
        clips=clips,
        total_duration_ms=sum(c.duration_ms for c in clips),
    )