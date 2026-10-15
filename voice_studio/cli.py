from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from voice_studio.config import DEFAULT_OUTPUT
from voice_studio.graph import run_pipeline
from voice_studio.story import list_stories, load_story


def _parse_voice_overrides(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--voice expects speaker=voice, got {item!r}")
        k, v = item.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="voice_studio")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--story", help="Story slug (see --list-stories)")
    src.add_argument("--brief", help="Inline brief text")
    src.add_argument("--brief-file", help="Path to a brief text file")
    src.add_argument("--list-stories", action="store_true",
                     help="List available stories and exit")

    p.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT))
    p.add_argument("--voice", action="append", default=[], metavar="SPEAKER=VOICE",
                   help="Override a voice for this run; repeatable")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


async def _run(args: argparse.Namespace) -> int:
    overrides: dict[str, str] = {}
    brief: str | None = None

    if args.story:
        story = load_story(args.story)
        brief = story.brief
        overrides.update(story.voices)
    elif args.brief_file:
        brief = Path(args.brief_file).read_text(encoding="utf-8").strip()
    elif args.brief:
        brief = args.brief

    if not brief:
        print("no brief supplied (use --story, --brief, or --brief-file)",
              file=sys.stderr)
        return 2

    # CLI overrides beat story pins.
    overrides.update(_parse_voice_overrides(args.voice))

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    state = await run_pipeline(brief, str(out), voice_overrides=overrides)
    script = state["script"]
    audio = state["audio"]

    (out / "script.json").write_text(
        script.model_dump_json(indent=2), encoding="utf-8")
    (out / "audio.json").write_text(
        audio.model_dump_json(indent=2), encoding="utf-8")

    if not args.quiet:
        print(f"\n=== {script.title} ===")
        for line in script.lines:
            print(f"  [{line.id}] {line.speaker} ({line.emotion}): {line.text}")
        print(f"\n--- {len(audio.clips)} clips, "
              f"{audio.total_duration_ms / 1000:.1f}s total ---")
        for clip in audio.clips:
            print(f"  {clip.path}  ({clip.duration_ms} ms, "
                  f"provider={clip.provider}, voice={clip.voice})")
        if audio.combined_path:
            print(f"\ncombined: {audio.combined_path}")

    return 0


def main() -> int:
    args = _parser().parse_args()

    if args.list_stories:
        for slug in list_stories():
            print(slug)
        return 0

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())