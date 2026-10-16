"""Every tool the orchestrator can call.

To add a new tool:

  ── STATELESS ─────────────────────────────────────────────────────
  Doesn't need session state. Write a function decorated with @tool,
  then add its name to STATELESS_TOOLS at the bottom of this block.

  ── SESSION-BOUND ─────────────────────────────────────────────────
  Needs access to session (paths, script, cast, audio). Define it as a
  closure inside build_session_tools(session), then add its name to the
  list returned by that function.

The orchestrator picks up whatever all_tools(session) returns.
Nothing else in the codebase needs to change.
"""
from __future__ import annotations
from pathlib import Path

from langchain.tools import tool

from voice_studio.config import VOICE_FAMILIES, INTER_LINE_PAUSE_MS


# ═══════════════════════════════════════════════════════════════════════
# STATELESS TOOLS
# ═══════════════════════════════════════════════════════════════════════

@tool
def list_voice_families() -> str:
    """List available voice families with descriptions. Call this before
    assigning voices so you know what's available."""
    return "\n".join(
        f"- {name}: {spec['description']}"
        for name, spec in VOICE_FAMILIES.items()
    )


@tool
def describe_family(name: str) -> str:
    """Return the full description and per-provider voice names for one family."""
    spec = VOICE_FAMILIES.get(name)
    if spec is None:
        return f"unknown family {name!r}; call list_voice_families first"
    voices = "\n".join(f"  {p}: {v}" for p, v in spec["voices"].items())
    return f"{name}\n{spec['description']}\nvoices:\n{voices}"


@tool
def list_stories() -> str:
    """List saved story slugs available for replay or loading."""
    from voice_studio.story import list_stories as _list
    slugs = _list()
    return "\n".join(slugs) if slugs else "(no stories saved)"


STATELESS_TOOLS = [
    list_voice_families,
    describe_family,
    list_stories,
    # ← add new stateless tools here
]


# ═══════════════════════════════════════════════════════════════════════
# SESSION-BOUND TOOLS
# ═══════════════════════════════════════════════════════════════════════

def build_session_tools(session) -> list:
    """Tools that need session state. Closures over `session`."""

    from voice_studio.agents import write_script, assign_voices, produce_audio
    from voice_studio.story import save_story, load_story as _load_story_module
    from voice_studio.media import ffmpeg_available, silence_ms, concat_audio
    from voice_studio.schemas import SpeechLine, Script, VoiceCast, SpeakerVoice
    from voice_studio.tts import TTSRegistry

    # ── pipeline ────────────────────────────────────────────────────

    @tool
    async def generate_script(brief: str) -> str:
        """Write a script from a brief. Must run first."""
        sr = await write_script(brief)
        session.script = sr.script
        session.story_toml = sr.story_toml
        session.save()
        return (
            f"Generated '{sr.script.title}' with {len(sr.script.lines)} lines. "
            f"Speakers: {sorted({l.speaker for l in sr.script.lines})}."
        )

    @tool
    async def pick_voices() -> str:
        """Assign a voice family to each speaker. Requires generate_script."""
        if session.script is None:
            return "no script yet — call generate_script first"
        cast = await assign_voices(session.script)
        session.cast = cast
        session.save()
        pairs = ", ".join(f"{a.speaker}={a.family}" for a in cast.assignments)
        return f"Cast: {pairs}"

    @tool
    async def synthesize_audio() -> str:
        """Render per-line audio. Requires generate_script + pick_voices."""
        if session.script is None or session.cast is None:
            return "need both a script and a voice cast first"
        bundle = await produce_audio(
            script=session.script, cast=session.cast,
            out_dir=session.out_dir / "audio",
        )
        session.audio = bundle
        session.save()
        return f"Rendered {len(bundle.clips)} clips, {bundle.total_duration_ms} ms."

    @tool
    async def stitch_final() -> str:
        """Concatenate clips into full.mp3. Requires synthesize_audio."""
        if session.audio is None:
            return "no audio yet — call synthesize_audio first"
        if not ffmpeg_available():
            return "ffmpeg not on PATH; skipping stitch"
        out_dir = session.out_dir / "audio"
        gap = out_dir / "_gap.mp3"
        silence_ms(INTER_LINE_PAUSE_MS, gap)
        combined = out_dir / "full.mp3"
        concat_audio([Path(c.path) for c in session.audio.clips], combined, gap_path=gap)
        session.audio = session.audio.model_copy(update={"combined_path": str(combined)})
        session.save()
        return f"Stitched: {combined}"

    @tool
    async def save_story_toml(slug: str) -> str:
        """Persist the current story under stories/<slug>.toml for replay."""
        if session.script is None:
            return "no script yet — call generate_script first"
        voices = session.cast.as_lookup() if session.cast else {}
        path = save_story(
            slug=slug,
            title=session.script.title,
            brief=session.story_toml or "",
            description="",
            voices=voices,
            script_json=session.script.model_dump_json(indent=2),
        )
        return f"Saved {path}"

    # ── script editing ──────────────────────────────────────────────

    @tool
    async def rewrite_line(line_id: str, instruction: str) -> str:
        """Rewrite one line of the script in place, leaving the rest
        untouched. Use when the user says 'make L3 funnier' or 'L5
        should sound nervous'. `instruction` is the user's intent in
        plain language."""
        if session.script is None:
            return "no script yet — call generate_script first"

        target = next((l for l in session.script.lines if l.id == line_id), None)
        if target is None:
            return f"no line {line_id}"

        from langchain.agents import create_agent
        from voice_studio.config import build_model

        agent = create_agent(
            model=build_model("creative"),
            tools=[],
            system_prompt=(
                "Rewrite one spoken line from a script. Keep the same id "
                "and speaker. Match the surrounding style. Do not add "
                "stage directions inside the text. Return only the new line."
            ),
            response_format=SpeechLine,
        )
        result = await agent.ainvoke({"messages": [{
            "role": "user",
            "content": (
                f"Script style: {session.script.style}\n"
                f"Current line: {target.model_dump_json()}\n"
                f"Instruction: {instruction}"
            ),
        }]})
        new_line = result.get("structured_response")
        if new_line is None:
            return "rewrite failed — model returned no structured response"

        # Preserve identity — the model shouldn't be trusted to keep these.
        new_line = new_line.model_copy(update={"id": line_id, "speaker": target.speaker})

        session.script.lines = [
            new_line if l.id == line_id else l for l in session.script.lines
        ]
        session.save()
        return f"Rewrote {line_id}: {new_line.text}"

    @tool
    def swap_speaker(line_id: str, new_speaker: str) -> str:
        """Change who says a line. Does not re-render audio — call
        rerender_line or synthesize_audio afterwards if you need fresh clips."""
        if session.script is None:
            return "no script yet"
        for l in session.script.lines:
            if l.id == line_id:
                l.speaker = new_speaker
                session.save()
                known = session.cast and any(
                    a.speaker.lower() == new_speaker.lower()
                    for a in session.cast.assignments
                )
                suffix = "" if known or session.cast is None else \
                    f" (warning: '{new_speaker}' not in cast)"
                return f"{line_id} now spoken by {new_speaker}{suffix}"
        return f"no line {line_id}"

    @tool
    def set_line_delivery(
        line_id: str,
        emotion: str | None = None,
        intensity: float | None = None,
        rate: float | None = None,
        pitch: float | None = None,
    ) -> str:
        """Adjust delivery of one line. Any argument left as None is unchanged.
        intensity 0..1, rate 0.5..2.0, pitch -50..50 (Hz)."""
        if session.script is None:
            return "no script yet"
        for l in session.script.lines:
            if l.id == line_id:
                if emotion is not None:   l.emotion = emotion
                if intensity is not None: l.intensity = max(0.0, min(1.0, intensity))
                if rate is not None:      l.rate = max(0.5, min(2.0, rate))
                if pitch is not None:     l.pitch = max(-50.0, min(50.0, pitch))
                session.save()
                return (f"{line_id}: emotion={l.emotion} intensity={l.intensity} "
                        f"rate={l.rate} pitch={l.pitch}")
        return f"no line {line_id}"

    @tool
    def remove_line(line_id: str) -> str:
        """Delete a line from the script. Any audio file for it stays on disk."""
        if session.script is None:
            return "no script yet"
        before = len(session.script.lines)
        session.script.lines = [l for l in session.script.lines if l.id != line_id]
        if len(session.script.lines) == before:
            return f"no line {line_id}"
        session.save()
        return f"Removed {line_id}. {len(session.script.lines)} lines remain."

    # ── voice editing ───────────────────────────────────────────────

    @tool
    def swap_voice(speaker: str, family: str) -> str:
        """Reassign one speaker to a different voice family. Call
        list_voice_families first to see valid names."""
        if session.cast is None:
            return "no cast yet — call pick_voices first"
        if family not in VOICE_FAMILIES:
            return f"unknown family {family!r}; call list_voice_families"
        for a in session.cast.assignments:
            if a.speaker.lower() == speaker.lower():
                a.family = family
                a.rationale = "manually reassigned"
                session.save()
                return f"{a.speaker} → {family}"
        return f"no speaker {speaker} in cast"

    @tool
    async def preview_voice(
        family: str,
        phrase: str = "The quick brown fox jumps over the lazy dog.",
    ) -> str:
        """Render a short sample of a voice family so the user can audition
        it before committing. Saves under <session>/previews/."""
        if family not in VOICE_FAMILIES:
            return f"unknown family {family!r}; call list_voice_families"

        registry = TTSRegistry(cast={"preview": family})
        line = SpeechLine(id="preview", speaker="preview", text=phrase)
        out = session.out_dir / "previews"
        clip = await registry.synthesize(line, out)
        return (f"Preview saved: {clip.path} "
                f"({clip.duration_ms} ms, {clip.provider}/{clip.voice})")

    # ── audio editing ───────────────────────────────────────────────

    @tool
    async def rerender_line(line_id: str) -> str:
        """Re-synthesize one line's audio. Use after rewrite_line or
        set_line_delivery, or when a single clip failed. Leaves other
        clips alone and refreshes total_duration_ms."""
        if session.script is None or session.cast is None or session.audio is None:
            return "need script, cast, and existing audio first"

        line = next((l for l in session.script.lines if l.id == line_id), None)
        if line is None:
            return f"no line {line_id}"

        registry = TTSRegistry(cast=session.cast.as_lookup())
        new_clip = await registry.synthesize(line, session.out_dir / "audio")

        clips = [new_clip if c.line_id == line_id else c for c in session.audio.clips]
        session.audio = session.audio.model_copy(update={
            "clips": clips,
            "total_duration_ms": sum(c.duration_ms for c in clips),
        })
        session.save()
        return f"Re-rendered {line_id}: {new_clip.path} ({new_clip.provider}/{new_clip.voice})"

    # ── story loading ───────────────────────────────────────────────

    @tool
    def load_story(slug: str) -> str:
        """Load a saved story into this session, replacing the current
        script and cast. Use list_stories first to see slugs."""
        try:
            story = _load_story_module(slug)
        except FileNotFoundError as e:
            return str(e)

        if story.script_path:
            session.script = Script.model_validate_json(
                story.script_path.read_text(encoding="utf-8"))
        if story.voices:
            session.cast = VoiceCast(assignments=[
                SpeakerVoice(speaker=s, family=f, rationale="from story TOML")
                for s, f in story.voices.items()
            ])
        session.save()
        lines = len(session.script.lines) if session.script else 0
        return f"Loaded '{story.title}' ({lines} lines, {len(story.voices)} voices)"

    # ── deliverables ────────────────────────────────────────────────

    @tool
    def export_transcript() -> str:
        """Write a plain-text transcript of the current script to
        <session>/transcript.txt."""
        if session.script is None:
            return "no script yet"
        lines = [f"{l.speaker}: {l.text}" for l in session.script.lines]
        out = session.out_dir / "transcript.txt"
        out.write_text(
            f"{session.script.title}\n\n" + "\n".join(lines),
            encoding="utf-8",
        )
        return f"Wrote {out}"

    @tool
    def export_srt() -> str:
        """Write an .srt subtitle file. Only works if the TTS provider
        returned word timings (currently Edge)."""
        if session.audio is None:
            return "no audio yet"
        if not any(c.word_timings for c in session.audio.clips):
            return ("no word timings available — the providers used don't "
                    "return them. Try Edge as a fallback provider.")

        def _ts(ms: int) -> str:
            h, rem = divmod(ms, 3_600_000)
            m, rem = divmod(rem, 60_000)
            s, ms = divmod(rem, 1000)
            return f"{h:02}:{m:02}:{s:02},{ms:03}"

        out = session.out_dir / "captions.srt"
        cursor = 0
        entries: list[str] = []
        cue = 1
        for clip in session.audio.clips:
            start = cursor
            end = cursor + clip.duration_ms
            if clip.word_timings:
                text = " ".join(w.word for w in clip.word_timings)
                entries.append(f"{cue}\n{_ts(start)} --> {_ts(end)}\n{text}\n")
                cue += 1
            cursor = end
        out.write_text("\n".join(entries), encoding="utf-8")
        return f"Wrote {out} ({cue - 1} cues)"

    @tool
    def export_show_notes() -> str:
        """Write a markdown summary of the session — title, cast, line
        list, file paths — to <session>/show_notes.md."""
        if session.script is None:
            return "no script yet"
        md: list[str] = [f"# {session.script.title}", "",
                         f"*Style: {session.script.style}*", ""]
        if session.cast:
            md.append("## Cast")
            for a in session.cast.assignments:
                md.append(f"- **{a.speaker}** — {a.family} — {a.rationale}")
            md.append("")
        md.append("## Lines")
        for l in session.script.lines:
            md.append(f"- `{l.id}` **{l.speaker}** ({l.emotion}, "
                      f"i={l.intensity}): {l.text}")
        if session.audio:
            md += ["", "## Files"]
            combined = session.audio.combined_path or "(not stitched)"
            md.append(f"- Combined: `{combined}`")
            md.append(f"- Clips: {len(session.audio.clips)}, "
                      f"{session.audio.total_duration_ms / 1000:.1f}s total")
        out = session.out_dir / "show_notes.md"
        out.write_text("\n".join(md), encoding="utf-8")
        return f"Wrote {out}"

    # ── filesystem ──────────────────────────────────────────────────

    @tool
    def write_file(path: str, content: str) -> str:
        """Write text to a file inside the session output directory.
        Creates parent directories. Relative paths resolve under the
        session directory; absolute paths are allowed but discouraged."""
        p = Path(path)
        if not p.is_absolute():
            p = session.out_dir / p
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars to {p}"

    @tool
    def read_file(path: str) -> str:
        """Read a text file. Relative paths resolve under the session dir."""
        p = Path(path)
        if not p.is_absolute():
            p = session.out_dir / p
        if not p.exists():
            return f"no such file: {p}"
        return p.read_text(encoding="utf-8")

    @tool
    def list_files(subdir: str = "") -> str:
        """List files in the session output directory, or a subdirectory."""
        base = session.out_dir / subdir if subdir else session.out_dir
        if not base.exists():
            return f"no such directory: {base}"
        files = [
            str(p.relative_to(session.out_dir))
            for p in sorted(base.rglob("*"))
            if p.is_file()
        ]
        return "\n".join(files) if files else "(empty)"

    filesystem = [
        write_file,
        read_file,
        list_files,
    ]
    tools = [
        generate_script,
        pick_voices,
        synthesize_audio,
        stitch_final,
        save_story_toml,
        load_story,
        list_stories,
    ] + filesystem

    if session.script is not None:
        tools += [
            rewrite_line,
            swap_speaker,
            set_line_delivery,
            remove_line,
            export_transcript,
        ]

    if session.cast is not None:
        tools += [swap_voice, preview_voice]

    if session.audio is not None:
        tools += [rerender_line, export_srt, export_show_notes]

    return tools


def all_tools(session) -> list:
    """Every tool the orchestrator can use this turn."""
    return STATELESS_TOOLS + build_session_tools(session)