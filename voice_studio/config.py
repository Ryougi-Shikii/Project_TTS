"""
voice_studio/config.py
======================

Single source of truth. To change behaviour, edit here — not elsewhere:

  • swap an LLM      → MODELS
  • add/reorder TTS  → TTS_CHAIN
  • change a voice   → VOICE_POOLS  (per-provider pools)
  • pin a voice      → stories/<slug>.toml [voices]  (per-story)
  • tweak pause      → INTER_LINE_PAUSE_MS
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model


# ═══════════════════════════════════════════════════════════════════════
# 1. LLM MODELS
# ═══════════════════════════════════════════════════════════════════════

MODELS: dict[str, dict[str, Any]] = {
    "creative": {
        "primary":     ("openai/gpt-oss-120b", "groq"),
        "fallbacks": [
            ("qwen/qwen3.8-27b",      "groq"),
            ("gemini-3.5-flash-lite", "google-genai"),
        ],
        "temperature": 0.9,
        "max_tokens":  3500,
        "timeout":     600,
    },
    "director": {
        "primary":     ("openai/gpt-oss-120b", "groq"),
        "fallbacks": [
            ("qwen/qwen3.8-27b",      "groq"),
            ("gemini-3.5-flash-lite", "google-genai"),
        ],
        "temperature": 0.3,
        "max_tokens":  2300,
        "timeout":     600,
    },
}


def build_model(role: str):
    spec = MODELS[role]

    def _make(entry: tuple[str, str]):
        name, provider = entry
        return init_chat_model(
            name,
            model_provider=provider,
            temperature=spec["temperature"],
            timeout=spec.get("timeout", 600),
            max_tokens=spec["max_tokens"],
        )

    primary = _make(spec["primary"])
    fallbacks = [_make(e) for e in spec.get("fallbacks", [])]
    if not fallbacks:
        return primary
    return primary.with_fallbacks(fallbacks, exceptions_to_handle=(Exception,))


# ═══════════════════════════════════════════════════════════════════════
# 2. TTS CHAIN  — order = priority. First provider that succeeds wins.
# ═══════════════════════════════════════════════════════════════════════
#
# To add a provider:
#   1. write voice_studio/tts/<name>_provider.py  (subclass TTSProvider)
#   2. append one dict below
#   3. optionally add <name> to VOICE_POOLS
#
# Every provider's __init__ must accept:
#     (default_voice, voice_resolver=None, **whatever_is_in_args)

TTS_CHAIN: list[dict[str, Any]] = [
    {
        "name":      "deepgram",
        "class":     "voice_studio.tts.deepgram_provider:DeepgramTTSProvider",
        "args":      {"model": "aura-asteria-en", "default_voice": "aura-asteria-en"},
        "extension": "mp3",
    },
    {
        "name":      "orpheus",
        "class":     "voice_studio.tts.orpheus_provider:OrpheusProvider",
        "args":      {"model": "canopylabs/orpheus-v1-english", "default_voice": "autumn"},
        "extension": "wav",
    },
    {
        "name":      "gemini",
        "class":     "voice_studio.tts.gemini_provider:GeminiTTSProvider",
        "args":      {"model": "gemini-2.5-flash-preview-tts", "default_voice": "Kore"},
        "extension": "wav",
    },
    {
        "name":      "edge",
        "class":     "voice_studio.tts.edge_provider:EdgeTTSProvider",
        "args":      {"default_voice": "en-US-GuyNeural"},
        "extension": "mp3",
    },
]


# ═══════════════════════════════════════════════════════════════════════
# 3. VOICE POOLS  — per-provider voices, assigned by speaker order
# ═══════════════════════════════════════════════════════════════════════

VOICE_POOLS: dict[str, list[str]] = {
    "deepgram": ["aura-asteria-en", "aura-orion-en", "aura-stella-en",
                 "aura-zeus-en", "aura-luna-en"],
    "orpheus":  ["autumn", "diana", "hannah", "austin", "daniel", "troy"],
    "gemini":   ["Kore", "Orus", "Puck", "Charon", "Aoede", "Fenrir"],
    "edge":     ["en-US-GuyNeural", "en-US-JennyNeural", "en-GB-RyanNeural",
                 "en-US-AriaNeural", "en-AU-NatashaNeural"],
}


# ═══════════════════════════════════════════════════════════════════════
# 4. PATHS
# ═══════════════════════════════════════════════════════════════════════

_ROOT          = Path(__file__).resolve().parent.parent
STORIES_DIR    = _ROOT / "stories"
DEFAULT_OUTPUT = Path("./output")


# ═══════════════════════════════════════════════════════════════════════
# 5. PIPELINE KNOBS
# ═══════════════════════════════════════════════════════════════════════

INTER_LINE_PAUSE_MS = 250