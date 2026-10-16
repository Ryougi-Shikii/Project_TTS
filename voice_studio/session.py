"""Session: persistent state of one conversation with the orchestrator."""
from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import Optional

from voice_studio.schemas import Script, VoiceCast, AudioBundle


class Session:
    def __init__(self, out_dir: Path, id: str | None = None):
        self.id = id or uuid.uuid4().hex[:8]
        self.out_dir = out_dir
        self.script: Optional[Script] = None
        self.story_toml: Optional[str] = None
        self.cast: Optional[VoiceCast] = None
        self.audio: Optional[AudioBundle] = None
        self.history: list[dict] = []

    @property
    def path(self) -> Path:
        return self.out_dir / "session.json"

    def save(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "id": self.id,
            "script": self.script.model_dump() if self.script else None,
            "story_toml": self.story_toml,
            "cast": self.cast.model_dump() if self.cast else None,
            "audio": self.audio.model_dump() if self.audio else None,
            "history": self.history,
        }, indent=2), encoding="utf-8")
        if self.script:
            (self.out_dir / "script.json").write_text(
                self.script.model_dump_json(indent=2), encoding="utf-8")
        if self.cast:
            (self.out_dir / "cast.json").write_text(
                self.cast.model_dump_json(indent=2), encoding="utf-8")
        if self.audio:
            (self.out_dir / "audio.json").write_text(
                self.audio.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, out_dir: Path) -> "Session":
        data = json.loads((out_dir / "session.json").read_text(encoding="utf-8"))
        s = cls(out_dir=out_dir, id=data["id"])
        s.script = Script.model_validate(data["script"]) if data.get("script") else None
        s.story_toml = data.get("story_toml")
        s.cast = VoiceCast.model_validate(data["cast"]) if data.get("cast") else None
        s.audio = AudioBundle.model_validate(data["audio"]) if data.get("audio") else None
        s.history = data.get("history", [])
        return s


def find_session(output_root: Path, sid: str) -> Session:
    direct = output_root / sid
    if (direct / "session.json").exists():
        return Session.load(direct)
    for p in output_root.glob("*/session.json"):
        if p.parent.name == sid:
            return Session.load(p.parent)
    raise FileNotFoundError(f"no session with id {sid!r}")


def list_sessions(output_root: Path) -> list[dict]:
    out = []
    for p in sorted(output_root.glob("*/session.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "id": d.get("id", p.parent.name),
            "dir": str(p.parent),
            "title": (d.get("script") or {}).get("title") if d.get("script") else None,
            "turns": sum(1 for m in d.get("history", []) if m.get("role") == "user"),
            "has_audio": bool(d.get("audio")),
        })
    return out


def state_summary(session: Session) -> str:
    bits = [f"session {session.id}"]
    if session.script:
        bits.append(f"script: '{session.script.title}' ({len(session.script.lines)} lines)")
    if session.cast:
        pairs = ", ".join(f"{a.speaker}={a.family}" for a in session.cast.assignments)
        bits.append(f"cast: {pairs}")
    if session.audio:
        bits.append(f"audio: {len(session.audio.clips)} clips, {session.audio.total_duration_ms} ms")
        if session.audio.combined_path:
            bits.append(f"stitched: {session.audio.combined_path}")
    bits.append(f"turns: {sum(1 for m in session.history if m.get('role') == 'user')}")
    return "\n".join(bits)