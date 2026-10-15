```markdown
# voice-studio

A config-driven, multi-agent pipeline that turns a one-paragraph brief into
a fully voiced script — dialogue, delivery metadata, per-line audio, and a
stitched final mix.

Two LLM agents write and direct. A declarative TTS chain with automatic
fallback speaks. Voice assignment, model selection, and provider priority
all live in one file.

```
brief ──► script agent ──► audio agent ──► TTS chain ──► ffmpeg ──► full.mp3
          (creative)       (director)      (fallbacks)
```

---

## Quickstart

```bash
git clone https://github.com/<you>/voice-studio.git
cd voice-studio

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Fill in whichever keys you have. Missing keys just disable that provider.

python -m voice_studio --list-stories
python -m voice_studio --story two_dogs -o out/two_dogs
```

You need **ffmpeg** on `PATH` for the final stitch. Every provider beyond
`edge-tts` needs its own API key; `edge-tts` is local and needs nothing.

---

## The two agents

**Script agent** (`agents/script_agent.py`) — one call, structured output.
Takes a brief, returns a `Script` Pydantic object:

```python
class Script(BaseModel):
    title: str
    style: str
    language: str = "en"
    lines: list[SpeechLine]

class SpeechLine(BaseModel):
    id: str                    # "L1", "L2", ...
    speaker: str               # character name, not voice name
    text: str
    emotion: str = "neutral"
    intensity: float = 0.5     # 0..1
    rate: float = 1.0          # 0.5..2.0
    pitch: float = 0.0         # Hz, -50..50
    volume: float = 0.0        # %,  -50..50
    pauses: list[Pause]        # after which word, how long
    emphasis: list[str]        # words to stress
    voice_hint: str | None
    visual_cue: str | None     # reserved for a future video stage
```

**Audio director** (`agents/audio_agent.py`) — runs a tool-use loop. It
calls `synthesize_speech(line_id)` once per line, in order. The tool takes
an ID, never free text, so the LLM cannot corrupt the script. A
`fill_missing` pass afterwards guarantees a complete bundle even if the
director skips a line.

Both agents use `ModelRetryMiddleware` and `ToolRetryMiddleware` for
transient failures.

---

## TTS chain and fallback

`TTS_CHAIN` in `config.py` is an ordered list. For each line, the registry
tries providers in order and uses the first that succeeds.

```python
TTS_CHAIN = [
    {"name": "orpheus",  "class": "...:OrpheusProvider",     "extension": "wav", ...},
    {"name": "deepgram", "class": "...:DeepgramTTSProvider", "extension": "mp3", ...},
    {"name": "gemini",   "class": "...:GeminiTTSProvider",   "extension": "wav", ...},
    {"name": "edge",     "class": "...:EdgeTTSProvider",     "extension": "mp3", ...},
]
```

Providers that fail to construct (missing key, missing SDK, missing
binary) are skipped at startup with a warning. The chain still runs with
whatever's left. If all providers fail on a given line, that's a hard
error — there is no silent placeholder.

| Provider   | SDK             | Env var              | Word timings | Style control |
|------------|-----------------|----------------------|:------------:|:-------------:|
| `deepgram` | `deepgram-sdk`  | `DEEPGRAM_API_KEY`   |              |               |
| `orpheus`  | `groq`          | `GROQ_API_KEY`       |              | ✓             |
| `gemini`   | `google-genai`  | `GOOGLE_API_KEY`     |              | ✓             |
| `edge`     | `edge-tts`      | —                    | ✓            |               |

Only `edge` returns word-level timing. Only `orpheus` and `gemini` accept
delivery instructions (emotion, intensity, rate) beyond raw rate/pitch.

---

## Voice resolution

Voices are not a `speaker → voice` dict. They're a function:

```python
def resolve(provider_name: str, speaker: str) -> str | None
```

`VoiceResolver` implements that function with three tiers, highest first:

1. **Explicit override** — `[voices]` block in the story TOML, or a
   `--voice speaker=voice` CLI flag.
2. **Per-provider pool** — `VOICE_POOLS[provider]`, indexed by the
   speaker's sorted position in the script.
3. **Provider default** — `default_voice` in `TTS_CHAIN[...]["args"]`.

The pool index is stable: speakers are sorted, assigned a slot, and every
provider in the chain uses the same slot. A character voiced by `autumn`
in Orpheus gets `en-US-GuyNeural` in Edge because both are `pool[0]`, not
because anyone mapped them.

If the chain falls back mid-run, the same character keeps its *role*
(first speaker, second speaker) even as the *voice* changes. Consistency
without hardcoding.

---

## Adding a story

Create `stories/kayfabe.toml`:

```toml
title       = "Kayfabe"
description = "Two wrestlers argue about whether the rivalry is real."

brief = """
Two professional wrestlers, alone backstage after a sold-out show, argue
about whether the rivalry they've maintained for six years was ever
real. Four to six lines. Neither raises their voice.
"""

# Optional. Pin specific voices; omit for pool assignment.
[voices]
wrestler_a = "troy"
wrestler_b = "daniel"
```

Then:

```bash
python -m voice_studio --story kayfabe
```

No code change. The `--list-stories` command picks it up automatically.

---

## Adding a TTS provider

**Step 1.** Write `voice_studio/tts/qwen_provider.py`. Subclass
`TTSProvider`, accept `default_voice`, `voice_resolver`, and whatever
kwargs your provider needs:

```python
from pathlib import Path
from voice_studio.schemas import SpeechLine, AudioClip
from voice_studio.tts.base import TTSProvider, TTSUnavailable

class QwenTTSProvider(TTSProvider):
    name = "qwen"

    def __init__(self, model: str, default_voice: str, voice_resolver=None):
        super().__init__(default_voice, voice_resolver)
        # store model, build client, raise TTSUnavailable on missing key
        self.model = model

    async def synthesize(self, line: SpeechLine, out_path: Path) -> AudioClip:
        voice = self._voice_for(line.speaker)
        # ... call your API, write bytes to out_path ...
        return AudioClip(
            line_id=line.id, speaker=line.speaker, text=line.text,
            path=str(out_path), voice=voice, provider=self.name,
            duration_ms=0, format="wav", word_timings=[],
        )
```

`_voice_for()` is inherited. Don't reimplement it.

**Step 2.** Append one dict to `TTS_CHAIN` in `config.py`:

```python
{
    "name":      "qwen",
    "class":     "voice_studio.tts.qwen_provider:QwenTTSProvider",
    "args":      {"model": "qwen-tts-v1", "default_voice": "Ethan"},
    "extension": "wav",
},
```

**Step 3.** Optionally add a pool:

```python
VOICE_POOLS["qwen"] = ["Ethan", "Chelsie", "Serena"]
```

The registry is not touched. The graph is not touched. The CLI is not
touched. There are no `if kind == "qwen"` branches anywhere, because
there are no `if kind ==` branches anywhere.

---

## Adding or swapping an LLM

Edit `MODELS` in `config.py`:

```python
MODELS = {
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
    "director": { ... },
}
```

Agents call `build_model("creative")` or `build_model("director")`. The
tuples are `(model_name, provider_name)` as accepted by LangChain's
`init_chat_model`. Fallbacks are applied via `.with_fallbacks(...)`.

---

## CLI

```
python -m voice_studio [--story SLUG | --brief TEXT | --brief-file PATH]
                       [-o DIR] [--voice SPEAKER=VOICE ...] [-q]

  --story SLUG          Run a story from stories/
  --brief TEXT          Inline brief
  --brief-file PATH     Read the brief from a file
  --list-stories        List available story slugs and exit
  -o, --output DIR      Output directory (default: ./output)
  --voice SPK=VOICE     Override a voice for this run (repeatable)
  -q, --quiet           Warnings only
```

Examples:

```bash
python -m voice_studio --list-stories
python -m voice_studio --story two_dogs -o out/two_dogs
python -m voice_studio --story manic --voice founder=troy
python -m voice_studio --brief "Two baristas argue about the espresso machine."
python -m voice_studio --brief-file ideas/kayfabe.txt
```

Output per run:

```
out/<name>/
  script.json      structured Script, indented
  audio.json       AudioBundle with clip paths and providers
  audio/
    L1.mp3         one file per line
    L2.wav
    ...
    _gap.mp3       silence inserted between clips
    full.mp3       stitched final mix
```

`audio.json` records which provider and which voice actually rendered each
line. If a fallback fired mid-run, you can see exactly where.

---

## Configuration

Everything routine lives in `voice_studio/config.py`.

| Want to…                   | Touch                                              |
|----------------------------|----------------------------------------------------|
| Add a story                | `stories/<slug>.toml`                              |
| Pin voices for a story     | `[voices]` block in that TOML                      |
| Change a provider's pool   | `VOICE_POOLS` in `config.py`                       |
| Add a TTS provider         | new `tts/<name>_provider.py` + one dict in `TTS_CHAIN` |
| Reorder fallback           | reorder `TTS_CHAIN`                                |
| Swap an LLM                | `MODELS` in `config.py`                            |
| Change voice policy        | `VoiceResolver.__call__` in `voices.py`            |
| Tweak inter-line pause     | `INTER_LINE_PAUSE_MS` in `config.py`               |
| Try a one-off              | CLI flags — no edit at all                         |

Environment variables:

```bash
GROQ_API_KEY=...        # orpheus, and the Groq-backed LLMs
GOOGLE_API_KEY=...      # gemini TTS, and Gemini-backed LLMs
DEEPGRAM_API_KEY=...    # deepgram TTS
```

Every provider is optional. The chain runs with whatever keys are present.

---

## Project layout

```
voice-studio/
├── stories/                       # one .toml per story — no code here
│   ├── two_dogs.toml
│   ├── manic.toml
│   └── ...
├── voice_studio/
│   ├── config.py                  # ← the file you actually edit
│   ├── voices.py                  # VoiceResolver: three-tier precedence
│   ├── story.py                   # load/list stories from disk
│   ├── cli.py                     # argparse entry point
│   ├── __main__.py                # python -m voice_studio
│   ├── graph.py                   # LangGraph pipeline
│   ├── schemas.py                 # Pydantic models
│   ├── agents/
│   │   ├── script_agent.py        # brief → Script
│   │   ├── audio_agent.py         # Script → AudioBundle
│   │   └── prompts.py
│   ├── tts/
│   │   ├── base.py                # TTSProvider ABC, VoiceResolverFn
│   │   ├── registry.py            # reads TTS_CHAIN, loads classes
│   │   ├── openai_provider.py
│   │   ├── deepgram_provider.py
│   │   ├── orpheus_provider.py
│   │   ├── gemini_provider.py
│   │   └── edge_provider.py
│   └── media/
│       └── ffmpeg.py              # silence, concat, mux
├── main.py                        # thin wrapper around cli:main
├── requirements.txt
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Pipeline internals

`graph.py` compiles a three-node LangGraph:

```
START → write_script → produce_audio → stitch_audio → END
```

**`write_script`** calls the script agent with the brief. Returns a
`Script` into state.

**`produce_audio`** builds a `VoiceResolver` from the script's speakers,
constructs a `TTSRegistry` with that resolver, and hands both to the audio
director. The director calls the synthesis tool per line. A `fill_missing`
pass renders any lines the LLM skipped. Returns an `AudioBundle`.

**`stitch_audio`** generates a `_gap.mp3` of `INTER_LINE_PAUSE_MS`,
concatenates all clips with the gap between them via ffmpeg's concat
demuxer, and writes `full.mp3`. Skipped silently if ffmpeg is absent —
the individual clips are still there.

State is a `TypedDict`:

```python
class PipelineState(TypedDict, total=False):
    brief: str
    output_dir: str
    voice_overrides: dict[str, str]
    script: Optional[Script]
    audio: Optional[AudioBundle]
    errors: list[str]
```

`run_pipeline()` is the async entry point. Use it directly if you're
embedding the pipeline:

```python
from voice_studio.graph import run_pipeline

state = await run_pipeline(
    brief="...",
    output_dir="./out",
    voice_overrides={"grandmaster": "troy"},
)
script = state["script"]
audio  = state["audio"]
```

---

## Provider notes

**Orpheus** understands inline non-verbal tags and capitalisation for
emphasis. `_prepare_text()` emits `<chuckle>`, `<sigh>`, `<laugh>`, etc.
for known emotions and uppercases emphasis words. Groq's hosted Orpheus
does **not** support `<break>` tags — the registry ignores `SpeechLine.pauses`
for this provider rather than emitting tags that get spoken aloud.

**Gemini TTS** is style-prompted. `_style_prefix()` turns `emotion`,
`intensity`, and `rate` into a natural-language instruction prepended to
the text. The response is 24 kHz 16-bit mono PCM, wrapped into a WAV
container by `_pcm_to_wav()`.

**Deepgram Aura** uses the voice name *as* the model name. `default_voice`
defaults to `model` if not given. The SDK's response shape has moved
between majors, so `_extract_bytes()` handles three known forms.

**Edge TTS** is the only local provider and the only one that returns
`WordTiming` objects, parsed from the `WordBoundary` stream. Useful if
you're building a video stage later.

---

## Requirements

- `ffmpeg` on `PATH` for the final stitch
- At least one of: `DEEPGRAM_API_KEY`, `GROQ_API_KEY`,
  `GOOGLE_API_KEY` — or just `pip install edge-tts` for a local fallback

---