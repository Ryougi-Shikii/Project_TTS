"""Everything you edit lives here.

  • swap an LLM         → MODELS
  • add/reorder TTS     → TTS_CHAIN
  • add/change a voice  → VOICE_FAMILIES
  • pin a story's cast  → stories/<slug>.toml [voices]
  • tweak pause         → INTER_LINE_PAUSE_MS
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model


# ═══════════════════════════════════════════════════════════════════════
# LLM MODELS
# ═══════════════════════════════════════════════════════════════════════
MODELS: dict[str, dict[str, Any]] = {
    "creative": {
        "primary": ("openai/gpt-oss-120b", "groq"),
        "fallbacks": [
            ("gemini-3.5-flash-lite", "google-genai"),
        ],
        "temperature": 0.9,
        "max_tokens":  5000,
        "timeout":     90,
    },
    "orchestrator": {
        "primary": ("gemini-3.5-flash-lite", "google-genai"),
        "fallbacks": [
            ("gemini-3.1-flash-lite", "google-genai"),
            ("openai/gpt-oss-120b", "groq"),
            ("qwen/qwen3.8-27b", "groq"),
        ],
        "temperature": 0.3,
        "max_tokens":  3000,
        "timeout":     90,
    },
    "voice_caster": {
        "primary": ("qwen/qwen3.8-27b", "groq"),
        "fallbacks": [
            ("gemini-3.5-flash-lite", "google-genai"),
        ],
        "temperature": 0.3,
        "max_tokens":  3000,
        "timeout":     90,
    },
}


def build_model(role: str):
    spec = MODELS[role]

    def _make(entry: tuple[str, str]):
        name, provider = entry
        return init_chat_model(
            name, model_provider=provider,
            temperature=spec["temperature"],
            timeout=spec.get("timeout", 600),
            max_tokens=spec["max_tokens"],
        )

    primary = _make(spec["primary"])
    fallbacks = [_make(e) for e in spec.get("fallbacks", [])]
    return primary.with_fallbacks(fallbacks, exceptions_to_handle=(Exception,)) if fallbacks else primary


# ═══════════════════════════════════════════════════════════════════════
# TTS CHAIN  — order = priority. First provider that succeeds on a line wins.
# ═══════════════════════════════════════════════════════════════════════

TTS_CHAIN: list[dict[str, Any]] = [
    {
        "name":      "orpheus",
        "class":     "voice_studio.tts:OrpheusProvider",
        "args":      {"model": "canopylabs/orpheus-v1-english", "default_voice": "autumn"},
        "extension": "wav",
    },
    {
        "name":      "deepgram",
        "class":     "voice_studio.tts:DeepgramTTSProvider",
        "args":      {"model": "aura-asteria-en", "default_voice": "aura-asteria-en"},
        "extension": "mp3",
    },
    {
        "name":      "gemini",
        "class":     "voice_studio.tts:GeminiTTSProvider",
        "args":      {"model": "gemini-2.5-flash-preview-tts", "default_voice": "Kore"},
        "extension": "wav",
    },
    {
        "name":      "edge",
        "class":     "voice_studio.tts:EdgeTTSProvider",
        "args":      {"default_voice": "en-US-GuyNeural"},
        "extension": "mp3",
    },
]


# ═══════════════════════════════════════════════════════════════════════
# VOICE FAMILIES — what the voice agent picks from. Each family maps to
# one voice per provider, so character identity survives a chain fallback.
# ═══════════════════════════════════════════════════════════════════════

VOICE_FAMILIES: dict[str, dict[str, Any]] = {
    "gravelly_older_male": {
        "description": (
            "Older male, low and gravelly, deliberate. Reads as authority, "
            "weariness, or menace. Good for villains, veterans, retired "
            "professionals — anyone with history."
        ),
        "voices": {
            "deepgram": "aura-orpheus-en",
            "orpheus":  "austin",
            "gemini":   "Charon",
            "edge":     "en-US-ChristopherNeural",
        },
    },
    "bright_young_female": {
        "description": (
            "Younger female, bright and quick. Eager, sharp, occasionally "
            "impatient. Good for rivals, proteges, fast-talking characters."
        ),
        "voices": {
            "deepgram": "aura-stella-en",
            "orpheus":  "hannah",
            "gemini":   "Kore",
            "edge":     "en-US-JennyNeural",
        },
    },
    "dry_conversational_male": {
        "description": (
            "Mid-range male, understated, conversational. Almost no affect. "
            "Good for deadpan comedy, narrators — anyone who refuses to "
            "sound like they're performing."
        ),
        "voices": {
            "deepgram": "aura-arcas-en",
            "orpheus":  "daniel",
            "gemini":   "Orus",
            "edge":     "en-US-GuyNeural",
        },
    },
    "dry_conversational_female": {
        "description": (
            "Mid-range female, deadpan, no performance. Good for cynical "
            "narrators, dry journalists, characters who've seen too much."
        ),
        "voices": {
            "deepgram": "aura-luna-en",
            "orpheus":  "diana",
            "gemini":   "Leda",
            "edge":     "en-US-AmberNeural",
        },
    },
    "warm_mid_female": {
        "description": (
            "Warm mid-range female. Reassuring without being saccharine. "
            "Good for narration, doctors, mothers — anyone calming someone "
            "else down."
        ),
        "voices": {
            "deepgram": "aura-asteria-en",
            "orpheus":  "autumn",
            "gemini":   "Aoede",
            "edge":     "en-US-AriaNeural",
        },
    },
    "smooth_young_male": {
        "description": (
            "Younger male, smooth and confident. Charming, salesy, or "
            "dangerous under the smile. Good for founders, con men, "
            "romantic leads."
        ),
        "voices": {
            "deepgram": "aura-zeus-en",
            "orpheus":  "troy",
            "gemini":   "Puck",
            "edge":     "en-US-BrandonNeural",
        },
    },
    "grand_narrator_female": {
        "description": (
            "Female with weight and gravity. Storyteller energy. Good for "
            "narrators, oracles, mothers delivering hard truths."
        ),
        "voices": {
            "deepgram": "aura-hera-en",
            "orpheus":  "autumn",
            "gemini":   "Aoede",
            "edge":     "en-GB-SoniaNeural",
        },
    },
    "anxious_mid_male": {
        "description": (
            "Mid-range male, slightly tense, higher energy. Nervous, "
            "defensive, overeager. Good for characters under pressure or "
            "trying too hard."
        ),
        "voices": {
            "deepgram": "aura-orion-en",
            "orpheus":  "daniel",
            "gemini":   "Fenrir",
            "edge":     "en-US-DavisNeural",
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════
# PATHS AND KNOBS
# ═══════════════════════════════════════════════════════════════════════

_ROOT          = Path(__file__).resolve().parent.parent
STORIES_DIR    = _ROOT / "stories"
DEFAULT_OUTPUT = Path("./output")

INTER_LINE_PAUSE_MS = 250