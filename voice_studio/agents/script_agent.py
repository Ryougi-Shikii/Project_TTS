from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware, ToolRetryMiddleware

from voice_studio.config import build_model
from voice_studio.schemas import Script
from voice_studio.agents.prompts import SCRIPT_PROMPT


def build_script_agent():
    return create_agent(
        model=build_model("creative"),
        tools=[],
        system_prompt=SCRIPT_PROMPT,
        response_format=Script,
        middleware=[
            ModelRetryMiddleware(max_retries=3),
            ToolRetryMiddleware(max_retries=2),
        ],
    )


async def write_script(brief: str) -> Script:
    agent = build_script_agent()
    result = await agent.ainvoke({"messages": [{"role": "user", "content": brief}]})
    script = result.get("structured_response")
    if script is None:
        raise RuntimeError("script agent returned no structured response")
    return script