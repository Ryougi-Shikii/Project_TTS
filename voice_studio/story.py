from __future__ import annotations
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from voice_studio.config import STORIES_DIR


@dataclass
class Story:
    slug: str
    title: str
    brief: str
    description: str = ""
    voices: dict[str, str] = field(default_factory=dict)   # speaker -> family
    script_path: Path | None = None                        # sibling .script.json


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
        raise FileNotFoundError(f"no story {slug_or_path!r}")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    script_path = p.with_suffix(".script.json")
    return Story(
        slug=p.stem,
        title=data.get("title", p.stem),
        brief=data["brief"].strip(),
        description=data.get("description", ""),
        voices={k.lower(): v for k, v in data.get("voices", {}).items()},
        script_path=script_path if script_path.exists() else None,
    )


def save_story(
    slug: str,
    title: str,
    brief: str,
    description: str = "",
    voices: dict[str, str] | None = None,
    script_json: str | None = None,
    stories_dir: Path | None = None,
) -> Path:
    """Write stories/<slug>.toml and, if given, stories/<slug>.script.json.

    The TOML is human-editable; the JSON preserves the exact script so
    replay is deterministic.
    """
    d = stories_dir or STORIES_DIR
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{slug}.toml"

    parts: list[str] = [f"title       = {_esc(title)}"]
    if description:
        parts.append(f"description = {_esc(description)}")
    parts += ["", 'brief = """', brief.strip(), '"""']
    if voices:
        parts += ["", "[voices]"]
        parts += [f"{s} = {_esc(f)}" for s, f in voices.items()]
    p.write_text("\n".join(parts) + "\n", encoding="utf-8")

    if script_json is not None:
        p.with_suffix(".script.json").write_text(script_json, encoding="utf-8")

    return p


def _esc(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'