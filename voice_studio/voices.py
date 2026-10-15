from __future__ import annotations
from typing import Callable

from voice_studio.config import VOICE_POOLS


class VoiceResolver:
    """
    Decides which voice a provider should use for a given speaker.

    Precedence (highest first):
      1. explicit override  (story TOML [voices], or CLI --voice)
      2. per-provider pool  (config.VOICE_POOLS, index-stable per speaker)
      3. provider default   (returned as None, provider falls back)
    """

    def __init__(
        self,
        speakers: list[str],
        explicit: dict[str, str] | None = None,
        pools: dict[str, list[str]] | None = None,
    ):
        self.pools = pools if pools is not None else VOICE_POOLS
        self.explicit = {k.lower(): v for k, v in (explicit or {}).items()}
        # Stable slot index per speaker so the same character maps to
        # pool[0] across every provider in the chain.
        ordered = sorted({s.lower() for s in speakers})
        self.order = {s: i for i, s in enumerate(ordered)}

    def __call__(self, provider: str, speaker: str) -> str | None:
        key = speaker.lower()
        if key in self.explicit:
            return self.explicit[key]
        pool = self.pools.get(provider)
        if not pool:
            return None
        idx = self.order.get(key, 0)
        return pool[idx % len(pool)]