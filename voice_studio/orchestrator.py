"""The conversational orchestrator: one turn of the session."""
from __future__ import annotations

import logging

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware

from voice_studio.config import build_model
from voice_studio.prompts import ORCHESTRATOR_PROMPT
from voice_studio.session import Session
from voice_studio.tools import all_tools
from voice_studio.log import timed
from voice_studio.log import TimingCallback


_REPL_HINT = (
    "\n\n[You are in an interactive session. The user will answer any "
    "question you ask. Act when the request is clear; ask when you're "
    "genuinely unsure.]"
)

_ONESHOT_HINT = (
    "\n\n[One-shot invocation. The user cannot respond to questions. "
    "Do not ask — either act, or produce a result and state the next step "
    "as a note.]"
)

def _text_of(msg) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text") or "")
        return "".join(parts).strip()
    return ""

async def chat(session: Session, message: str, *, one_shot: bool = False) -> str:
    with timed(f"chat(one_shot={one_shot})", level=logging.DEBUG):
        agent = create_agent(
            model=build_model("orchestrator"),
            tools=all_tools(session),
            system_prompt=ORCHESTRATOR_PROMPT + (_ONESHOT_HINT if one_shot else _REPL_HINT),
            middleware=[ModelRetryMiddleware(max_retries=2)],
        )

        session.history.append({"role": "user", "content": message})
        result = await agent.ainvoke(
            {"messages": session.history},
            config={"callbacks": [TimingCallback()]},
        )


        session.history = [
            m.model_dump()
            for m in result["messages"]
            if getattr(m, "type", None) != "system"
        ]

        reply = ""
        for m in reversed(result["messages"]):
            if getattr(m, "type", None) == "ai":
                text = _text_of(m)
                if text:
                    reply = text
                    break
        return reply

