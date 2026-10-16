from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from voice_studio.config import DEFAULT_OUTPUT
from voice_studio.session import Session, find_session, list_sessions, state_summary
from voice_studio.orchestrator import chat
from voice_studio.agents import write_script, assign_voices, produce_audio
from voice_studio.schemas import Script, VoiceCast, SpeakerVoice
from voice_studio.story import list_stories, load_story


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voice_studio",
        description="Conversational producer for voiced content.",
    )
    p.add_argument("request", nargs="?",
                   help="Message for the orchestrator. Omit to start a REPL.")
    p.add_argument("--resume", metavar="SESSION_ID",
                   help="Continue an existing session")
    p.add_argument("--sessions", action="store_true",
                   help="List sessions and exit")
    p.add_argument("--story", help="Deterministic replay of a saved story")
    p.add_argument("--list-stories", action="store_true")
    p.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT))
    p.add_argument("-q", "--quiet", action="store_true")
    return p


async def _repl(session: Session) -> int:
    print(f"session {session.id} — /state, /exit")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/exit", "/quit"):
            break
        if line == "/state":
            print(state_summary(session))
            continue
        try:
            reply = await chat(session, line, one_shot=False)
        except Exception:
            logging.getLogger("voice_studio").exception("chat failed")
            continue
        session.save()
        if reply:
            print(reply)
    session.save()
    print(f"saved: {session.out_dir}")
    return 0


async def _one_shot(session: Session, message: str) -> int:
    session.out_dir.mkdir(parents=True, exist_ok=True)
    try:
        reply = await chat(session, message, one_shot=True)
    except Exception:
        logging.getLogger("voice_studio").exception("chat failed")
        raise
    finally:
        session.save()
    if reply:
        print(reply)
    print(f"\nsession {session.id}  →  {session.out_dir}")
    return 0


async def _replay(story_slug: str, out: Path) -> int:
    story = load_story(story_slug)

    if story.script_path:
        script = Script.model_validate_json(
            story.script_path.read_text(encoding="utf-8"))
    else:
        sr = await write_script(story.brief)
        script = sr.script

    if story.voices:
        cast = VoiceCast(assignments=[
            SpeakerVoice(speaker=s, family=f, rationale="from story TOML")
            for s, f in story.voices.items()
        ])
    else:
        cast = await assign_voices(script)

    bundle = await produce_audio(script=script, cast=cast, out_dir=out / "audio")

    (out / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    (out / "cast.json").write_text(cast.model_dump_json(indent=2), encoding="utf-8")
    (out / "audio.json").write_text(bundle.model_dump_json(indent=2), encoding="utf-8")

    print(f"\n=== {script.title} ===")
    for line in script.lines:
        print(f"  [{line.id}] {line.speaker} ({line.emotion}): {line.text}")
    print(f"\n--- {len(bundle.clips)} clips, {bundle.total_duration_ms / 1000:.1f}s ---")
    for clip in bundle.clips:
        print(f"  {clip.path}  ({clip.duration_ms} ms, {clip.provider}/{clip.voice})")
    return 0


def main() -> int:
    args = _parser().parse_args()
    output_root = Path(args.output)

    if args.list_stories:
        for slug in list_stories():
            print(slug)
        return 0

    if args.sessions:
        rows = list_sessions(output_root) if output_root.exists() else []
        if not rows:
            print("(no sessions)")
            return 0
        for r in rows:
            title = r["title"] or "-"
            audio = "audio" if r["has_audio"] else "     "
            print(f"  {r['id']}  [{audio}]  {r['turns']:>2} turns  {title}")
        return 0

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)-22s %(message)s",
        datefmt="%H:%M:%S",
    )
    # logging.getLogger("httpx").setLevel(logging.WARNING)
    # logging.getLogger("httpcore").setLevel(logging.WARNING)
    # logging.getLogger("groq._base_client").setLevel(logging.WARNING)
    # logging.getLogger("langchain_core.callbacks.manager").setLevel(logging.ERROR)
    # logging.getLogger("google_genai").setLevel(logging.WARNING)

    if args.story:
        out = output_root / f"replay-{args.story}"
        out.mkdir(parents=True, exist_ok=True)
        return asyncio.run(_replay(args.story, out))

    if args.resume:
        try:
            session = find_session(output_root, args.resume)
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 2
    else:
        # Fresh id, then real directory named after it.
        tmp = Session(out_dir=output_root / "_tmp")
        session = Session(out_dir=output_root / tmp.id, id=tmp.id)

    if args.request:
        return asyncio.run(_one_shot(session, args.request))
    return asyncio.run(_repl(session))


if __name__ == "__main__":
    raise SystemExit(main())