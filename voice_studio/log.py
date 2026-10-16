from __future__ import annotations
import logging
import time
from contextlib import contextmanager

from langchain_core.callbacks import BaseCallbackHandler

log = logging.getLogger("voice_studio")


@contextmanager
def timed(label: str, *, level: int = logging.INFO):
    """Log entry, exit, and duration of a block. On exception, log the
    failure and re-raise."""
    t0 = time.perf_counter()
    log.log(level, "→ %s", label)
    try:
        yield
    except Exception as e:
        dt = time.perf_counter() - t0
        log.error("✗ %s (%.2fs)  %s: %s", label, dt, type(e).__name__, e)
        raise
    else:
        dt = time.perf_counter() - t0
        log.log(level, "← %s (%.2fs)", label, dt)


class TimingCallback(BaseCallbackHandler):
    """One-line entry/exit for LLM and tool runs, deduplicated.

    LangChain delivers the same callback event more than once when a
    model is wrapped (structured output chains, bound runnables, etc.).
    We track active runs by run_id so a second delivery of the same
    event is dropped.
    """

    def __init__(self):
        self._llm_starts: dict[str, float] = {}
        self._tool_starts: dict[str, float] = {}

    @staticmethod
    def _key(run_id) -> str:
        return str(run_id)

    # ── LLM ─────────────────────────────────────────────────────────

    def on_llm_start(self, serialized, prompts, *, run_id=None, **kw):
        key = self._key(run_id)
        if key in self._llm_starts:
            return  # duplicate delivery of a run we already track
        self._llm_starts[key] = time.perf_counter()
        model = (serialized or {}).get("name") or "llm"
        log.info("  llm → %s", model)

    def on_llm_end(self, response, *, run_id=None, **kw):
        key = self._key(run_id)
        t0 = self._llm_starts.pop(key, None)
        if t0 is None:
            return  # already reported, or never started
        dt = time.perf_counter() - t0

        in_tok = out_tok = "?"
        model = "?"
        try:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)

            usage = getattr(msg, "usage_metadata", None) if msg else None
            if usage:
                in_tok = usage.get("input_tokens", "?")
                out_tok = usage.get("output_tokens", "?")

            # Providers disagree on where the model name lives. Try the
            # AIMessage response_metadata first, then llm_output.
            if msg is not None:
                meta = getattr(msg, "response_metadata", {}) or {}
                model = meta.get("model_name") or meta.get("model") or "?"
            if model == "?" and response.llm_output:
                model = response.llm_output.get("model_name") or "?"
        except Exception:
            pass

        log.info("  llm ← %s  %.2fs  in=%s out=%s", model, dt, in_tok, out_tok)

    def on_llm_error(self, error, *, run_id=None, **kw):
        key = self._key(run_id)
        t0 = self._llm_starts.pop(key, None)
        if t0 is None:
            return
        dt = time.perf_counter() - t0
        log.error("  llm ✗ %.2fs  %s: %s", dt, type(error).__name__, error)

    # ── tools ───────────────────────────────────────────────────────

    def on_tool_start(self, serialized, input_str, *, run_id=None, **kw):
        key = self._key(run_id)
        if key in self._tool_starts:
            return
        self._tool_starts[key] = time.perf_counter()
        name = (serialized or {}).get("name", "tool")
        log.info("    tool → %s", name)

    def on_tool_end(self, output, *, run_id=None, **kw):
        key = self._key(run_id)
        t0 = self._tool_starts.pop(key, None)
        if t0 is None:
            return
        dt = time.perf_counter() - t0
        log.info("    tool ← %.2fs", dt)

    def on_tool_error(self, error, *, run_id=None, **kw):
        key = self._key(run_id)
        t0 = self._tool_starts.pop(key, None)
        if t0 is None:
            return
        dt = time.perf_counter() - t0
        log.error("    tool ✗ %.2fs  %s", dt, error)