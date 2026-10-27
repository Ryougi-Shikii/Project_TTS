from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from langchain_core.prompts import ChatPromptTemplate
from logger import setup_logger, log_step

logger = setup_logger("script")


class CharacterSpec(BaseModel):
    name: str = Field(description="Character name, e.g. 'Miku', 'Detective Miller', 'Sarah'")
    gender: str = Field(description="'female', 'male', or 'neutral'")
    age_archetype: str = Field(description="'teen', 'young_adult', 'adult', 'elderly'")
    visual_dna: str = Field(
        description=(
            "Exact physical appearance: hair style/color, eyes, build, clothing, outfit details, accessories. "
            "Must be detailed, concrete, and consistent."
        )
    )
    theme_color: str = Field(description="Hex color code for subtitles, e.g. '#00d2ff', '#ff3366', '#ffcc00'")


class ScriptLine(BaseModel):
    id: str = Field(description="Unique line ID, e.g. L1, L2")
    speaker: str = Field(description="Speaker name matching one of the characters")
    text: str = Field(description="Spoken dialogue line (natural, snappy, written for the ear)")
    emotion: str = Field(description="Emotional delivery: e.g. 'playful', 'tense', 'urgent', 'deadpan'")
    camera_shot: str = Field(description="Camera framing: 'close-up on face', 'medium two-shot', 'over-the-shoulder'")
    visual_action: str = Field(description="Specific physical acting, expression, gesture, eye contact")


class VideoScript(BaseModel):
    title: str = Field(description="Catchy short title for the scene")
    setting: str = Field(description="Physical location, time of day, lighting, weather, and atmosphere")
    art_style: str = Field(description="Visual art style: e.g. 'Cinematic anime, Makoto Shinkai aesthetic, 16:9' or 'Gritty neo-noir, 16:9'")
    characters: List[CharacterSpec] = Field(description="All characters appearing in this scene")
    lines: List[ScriptLine] = Field(description="Sequence of 4 to 6 dialogue lines (~15 to 30 seconds total)")


SCRIPT_SYSTEM_PROMPT = """You are a master screenwriter and visual director.
Given ANY scene brief or query, create a tight 15 to 30 second scene.

Rules:
1. Infer characters and environment dynamically from the prompt (works for ANY genre: anime, sci-fi, noir, comedy, drama, etc.).
2. Define an immutable visual_dna for every character (hair, eyes, clothes, features) to guarantee visual continuity across shots.
3. Write 4 to 6 spoken lines that tell a compelling mini-story or banter.
4. Specify camera shot and physical acting for each frame.
"""


def _get_llm():
    """Build the structured LLM using Groq or Google GenAI."""
    groq_key = os.environ.get("GROQ_API_KEY")
    google_key = os.environ.get("GOOGLE_API_KEY")

    models = []
    if groq_key:
        try:
            from langchain_groq import ChatGroq
            models.append(ChatGroq(model_name="openai/gpt-oss-120b", temperature=0.8, timeout=60))
        except Exception:
            pass

    if google_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            models.append(ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.8, timeout=60))
        except Exception:
            pass

    if not models:
        raise RuntimeError("No LLM API keys found. Please set GROQ_API_KEY or GOOGLE_API_KEY in .env")

    primary = models[0]
    if len(models) > 1:
        return primary.with_fallbacks(models[1:], exceptions_to_handle=(Exception,))
    return primary


async def generate_script(topic: str) -> VideoScript:
    """Generate a dynamic script, character bible, and visual storyboard for ANY topic."""
    with log_step(logger, f"Generating script & character bible for query: '{topic}'"):
        llm = _get_llm()
        structured_llm = llm.with_structured_output(VideoScript)

        prompt = ChatPromptTemplate.from_messages([
            ("system", SCRIPT_SYSTEM_PROMPT),
            ("user", "Create a 15-30 second scene for the query: {topic}")
        ])

        chain = prompt | structured_llm
        script: VideoScript = await chain.ainvoke({"topic": topic})

        logger.info(f"Script generated: \"{script.title}\" | {len(script.characters)} characters | {len(script.lines)} lines")
        return script
