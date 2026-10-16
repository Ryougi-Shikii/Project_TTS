"""Subagents and their underlying operations.

  write_script   — LLM script writer, returns Script + TOML
  assign_voices  — LLM voice caster, returns VoiceCast
  produce_audio  — deterministic, no LLM

The orchestrator in orchestrator.py reaches these through tools.py.
"""
from __future__ import annotations
from pathlib import Path
import asyncio

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware, ToolRetryMiddleware

from voice_studio.config import build_model
from voice_studio.schemas import Script, ScriptResult, VoiceCast, AudioBundle
from voice_studio.prompts import SCRIPT_PROMPT, VOICE_PROMPT
from voice_studio.log import timed, TimingCallback
from voice_studio.tts import TTSRegistry


async def write_script(brief: str) -> ScriptResult:
    with timed("write_script"):
        agent = create_agent(
            model=build_model("creative"),
            tools=[],
            system_prompt=SCRIPT_PROMPT,
            response_format=ScriptResult,
            middleware=[
                ModelRetryMiddleware(max_retries=3),
                ToolRetryMiddleware(max_retries=2),
            ],
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": brief}]},
            config={"callbacks": [TimingCallback()]},
        )
        sr = result.get("structured_response")
        if sr is None:
            raise RuntimeError("script agent returned no structured response")
        return sr


async def assign_voices(script: Script) -> VoiceCast:
    # Local import — tools.py imports agents.py, so importing at module
    # top would be circular.
    with timed("assign_voices"):
        from voice_studio.tools import list_voice_families, describe_family

        agent = create_agent(
            model=build_model("voice_caster"),
            tools=[list_voice_families, describe_family],
            system_prompt=VOICE_PROMPT,
            response_format=VoiceCast,
            middleware=[ModelRetryMiddleware(max_retries=3)],
        )
        result = await agent.ainvoke(
            {
                "messages": [{
                    "role": "user",
                    "content": f"Assign voices to this script:\n\n{script.model_dump_json(indent=2)}",
                }]
            },
            config={"callbacks": [TimingCallback()]},
        )
        cast = result.get("structured_response")
        if cast is None:
            raise RuntimeError("voice agent returned no structured response")
        return cast



async def produce_audio(script: Script, cast: VoiceCast, out_dir: Path) -> AudioBundle:
    with timed(f"produce_audio ({len(script.lines)} lines)"):
        registry = TTSRegistry(cast=cast.as_lookup())
        out_dir.mkdir(parents=True, exist_ok=True)
        
        sem = asyncio.Semaphore(3)
        async def _one(line):
            async with sem:
                return await registry.synthesize(line, out_dir)
            
        clips = await asyncio.gather(*(_one(l) for l in script.lines))
        clips = list(clips)

        return AudioBundle(
            title=script.title,
            clips=clips,
            total_duration_ms=sum(c.duration_ms for c in clips),
        )