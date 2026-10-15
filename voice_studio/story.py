from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:      # Python < 3.11
    import tomli as tomllib      # type: ignore

from voice_studio.config import STORIES_DIR


@dataclass
class Story:
    slug: str
    title: str
    brief: str
    description: str = ""
    voices: dict[str, str] = field(default_factory=dict)


def list_stories(stories_dir: Path | None = None) -> list[str]:
    d = stories_dir or STORIES_DIR
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.toml"))


def load_story(slug_or_path: str, stories_dir: Path | None = None) -> Story:
    p = Path(slug_or_path)
    if not p.exists():
        p = (stories_dir or STORIES_DIR) / f"{slug_or_path}.toml"
    if not p.exists():
        raise FileNotFoundError(f"no story {slug_or_path!r} (looked in {p})")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return Story(
        slug=p.stem,
        title=data.get("title", p.stem),
        brief=data["brief"].strip(),
        description=data.get("description", ""),
        voices={k.lower(): v for k, v in data.get("voices", {}).items()},
    )