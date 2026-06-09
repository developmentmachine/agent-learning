"""
Hermes closed-loop learning — minimal simulation.

Mirrors three upstream mechanisms:
  1. Declarative memory  (MEMORY.md / USER.md) — tools/memory_tool.py
  2. Procedural memory   (skills via skill_manage) — tools/skill_manager_tool.py
  3. Background review   (post-turn fork) — agent/background_review.py
  4. Curator lifecycle   (usage telemetry + stale/archive) — agent/curator.py + tools/skill_usage.py
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

WriteOrigin = Literal["foreground", "background_review"]

ENTRY_DELIMITER = "\n§\n"
MEMORY_LIMIT = 2200
USER_LIMIT = 1375

DEFAULT_MEMORY_NUDGE_INTERVAL = 3  # turns
DEFAULT_SKILL_NUDGE_INTERVAL = 10  # tool iterations without skill_manage
DEFAULT_STALE_AFTER_DAYS = 30
DEFAULT_ARCHIVE_AFTER_DAYS = 90


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ── Declarative memory (MEMORY.md / USER.md) ───────────────────────────────


@dataclass
class MemoryStore:
    """Simplified MemoryStore — frozen snapshot + live entries."""

    memory_entries: list[str] = field(default_factory=list)
    user_entries: list[str] = field(default_factory=list)
    memory_limit: int = MEMORY_LIMIT
    user_limit: int = USER_LIMIT
    _snapshot: dict[str, str] = field(default_factory=dict)

    def load(self, mem_dir: Path) -> None:
        mem_dir.mkdir(parents=True, exist_ok=True)
        self.memory_entries = self._read(mem_dir / "MEMORY.md")
        self.user_entries = self._read(mem_dir / "USER.md")
        self._snapshot = {
            "memory": self._render_block("MEMORY", self.memory_entries, self.memory_limit),
            "user": self._render_block("USER PROFILE", self.user_entries, self.user_limit),
        }

    def system_prompt_block(self) -> str:
        return "\n\n".join(v for v in self._snapshot.values() if v)

    def tool_memory(
        self,
        action: str,
        *,
        target: str = "memory",
        content: str = "",
        old_text: str = "",
    ) -> dict[str, Any]:
        entries = self.memory_entries if target == "memory" else self.user_entries
        limit = self.memory_limit if target == "memory" else self.user_limit

        if action == "add":
            if content in entries:
                return {"success": True, "message": "no duplicate added", "target": target}
            projected = self._char_count(entries) + len(content) + len(ENTRY_DELIMITER) * max(len(entries), 1)
            if projected > limit:
                return {
                    "success": False,
                    "error": f"Memory at capacity ({projected}/{limit} chars). Consolidate first.",
                    "current_entries": entries,
                    "target": target,
                }
            entries.append(content)
            self._persist(target)
            return {"success": True, "message": "Entry added", "target": target}

        if action == "replace":
            idx = self._match_one(entries, old_text)
            if idx is None:
                return {"success": False, "error": "old_text must match exactly one entry", "target": target}
            entries[idx] = content
            self._persist(target)
            return {"success": True, "message": "Entry updated", "target": target}

        if action == "remove":
            idx = self._match_one(entries, old_text)
            if idx is None:
                return {"success": False, "error": "old_text must match exactly one entry", "target": target}
            entries.pop(idx)
            self._persist(target)
            return {"success": True, "message": "Entry removed", "target": target}

        return {"success": False, "error": f"unknown action {action}"}

    def _persist(self, target: str) -> None:
        # Live state on disk; snapshot refreshes next session (frozen pattern).
        pass  # caller writes files via save()

    def save(self, mem_dir: Path) -> None:
        mem_dir.mkdir(parents=True, exist_ok=True)
        (mem_dir / "MEMORY.md").write_text(ENTRY_DELIMITER.join(self.memory_entries), encoding="utf-8")
        (mem_dir / "USER.md").write_text(ENTRY_DELIMITER.join(self.user_entries), encoding="utf-8")

    @staticmethod
    def _read(path: Path) -> list[str]:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8").strip()
        return [e.strip() for e in text.split(ENTRY_DELIMITER) if e.strip()] if text else []

    @staticmethod
    def _char_count(entries: list[str]) -> int:
        if not entries:
            return 0
        return sum(len(e) for e in entries) + len(ENTRY_DELIMITER) * (len(entries) - 1)

    @staticmethod
    def _match_one(entries: list[str], needle: str) -> int | None:
        hits = [i for i, e in enumerate(entries) if needle in e]
        if len(hits) != 1:
            return None
        return hits[0]

    @staticmethod
    def _render_block(title: str, entries: list[str], limit: int) -> str:
        if not entries:
            return ""
        used = MemoryStore._char_count(entries)
        pct = int(used / limit * 100) if limit else 0
        body = ENTRY_DELIMITER.join(entries)
        return f"{'═' * 20}\n{title} [{pct}% — {used}/{limit} chars]\n{'═' * 20}\n{body}"


# ── Skill usage telemetry (.usage.json) ────────────────────────────────────


@dataclass
class UsageRecord:
    created_by: str | None = None
    agent_created: bool = False
    use_count: int = 0
    view_count: int = 0
    patch_count: int = 0
    last_used_at: str | None = None
    last_viewed_at: str | None = None
    last_patched_at: str | None = None
    created_at: str = field(default_factory=_now_iso)
    state: str = "active"
    pinned: bool = False
    archived_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_by": self.created_by,
            "agent_created": self.agent_created,
            "use_count": self.use_count,
            "view_count": self.view_count,
            "patch_count": self.patch_count,
            "last_used_at": self.last_used_at,
            "last_viewed_at": self.last_viewed_at,
            "last_patched_at": self.last_patched_at,
            "created_at": self.created_at,
            "state": self.state,
            "pinned": self.pinned,
            "archived_at": self.archived_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageRecord:
        return cls(
            created_by=data.get("created_by"),
            agent_created=bool(data.get("agent_created")),
            use_count=int(data.get("use_count") or 0),
            view_count=int(data.get("view_count") or 0),
            patch_count=int(data.get("patch_count") or 0),
            last_used_at=data.get("last_used_at"),
            last_viewed_at=data.get("last_viewed_at"),
            last_patched_at=data.get("last_patched_at"),
            created_at=data.get("created_at") or _now_iso(),
            state=data.get("state") or "active",
            pinned=bool(data.get("pinned")),
            archived_at=data.get("archived_at"),
        )


class UsageTracker:
    """Sidecar ~/.hermes/skills/.usage.json — mirrors tools/skill_usage.py."""

    def __init__(self, skills_dir: Path):
        self.path = skills_dir / ".usage.json"
        self.archive_dir = skills_dir / ".archive"
        self._data: dict[str, UsageRecord] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._data = {k: UsageRecord.from_dict(v) for k, v in raw.items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v.to_dict() for k, v in self._data.items()}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def bump_view(self, name: str) -> None:
        rec = self._ensure(name)
        rec.view_count += 1
        rec.last_viewed_at = _now_iso()
        self.save()

    def bump_patch(self, name: str) -> None:
        rec = self._ensure(name)
        rec.patch_count += 1
        rec.last_patched_at = _now_iso()
        self.save()

    def mark_agent_created(self, name: str) -> None:
        rec = self._ensure(name)
        rec.created_by = "agent"
        rec.agent_created = True
        self.save()

    def is_agent_created(self, name: str) -> bool:
        rec = self._data.get(name)
        return bool(rec and (rec.created_by == "agent" or rec.agent_created))

    def _ensure(self, name: str) -> UsageRecord:
        if name not in self._data:
            self._data[name] = UsageRecord()
        return self._data[name]

    def latest_activity(self, name: str) -> datetime | None:
        rec = self._data.get(name)
        if not rec:
            return None
        latest: datetime | None = None
        for ts in (rec.last_used_at, rec.last_viewed_at, rec.last_patched_at, rec.created_at):
            dt = _parse_iso(ts)
            if dt and (latest is None or dt > latest):
                latest = dt
        return latest

    def apply_lifecycle(
        self,
        skill_names: list[str],
        *,
        stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
        archive_after_days: int = DEFAULT_ARCHIVE_AFTER_DAYS,
        skills_dir: Path,
        now: datetime | None = None,
    ) -> list[str]:
        """Deterministic curator phase — no LLM."""
        now = now or datetime.now(timezone.utc)
        events: list[str] = []
        for name in skill_names:
            rec = self._data.get(name)
            if not rec or rec.pinned or not self.is_agent_created(name):
                continue
            activity = self.latest_activity(name)
            if activity is None:
                continue
            idle_days = (now - activity).days
            if idle_days >= archive_after_days and rec.state != "archived":
                src = skills_dir / name
                dst = self.archive_dir / name
                if src.exists():
                    self.archive_dir.mkdir(parents=True, exist_ok=True)
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.move(str(src), str(dst))
                rec.state = "archived"
                rec.archived_at = _now_iso()
                events.append(f"archived {name} (idle {idle_days}d)")
            elif idle_days >= stale_after_days and rec.state == "active":
                rec.state = "stale"
                events.append(f"stale {name} (idle {idle_days}d)")
        self.save()
        return events


# ── Write-origin provenance ────────────────────────────────────────────────


class WriteOriginContext:
    """Mirrors tools/skill_provenance.py ContextVar semantics."""

    def __init__(self) -> None:
        self._origin: WriteOrigin = "foreground"

    def set(self, origin: WriteOrigin) -> None:
        self._origin = origin

    def get(self) -> WriteOrigin:
        return self._origin

    def is_background_review(self) -> bool:
        return self._origin == "background_review"


# ── Nudge + background review orchestration ────────────────────────────────


@dataclass
class NudgeState:
    turns_since_memory: int = 0
    iters_since_skill: int = 0
    user_turn_count: int = 0
    memory_nudge_interval: int = DEFAULT_MEMORY_NUDGE_INTERVAL
    skill_nudge_interval: int = DEFAULT_SKILL_NUDGE_INTERVAL


@dataclass
class TurnRecord:
    user_message: str
    assistant_summary: str
    tool_iterations: int
    signals: list[str] = field(default_factory=list)


def detect_learning_signals(turn: TurnRecord) -> list[str]:
    """Rule-based stand-in for the LLM review fork."""
    text = (turn.user_message + " " + turn.assistant_summary).lower()
    signals: list[str] = []
    if any(p in text for p in ("prefer", "don't", "stop ", "remember", "always use")):
        signals.append("user_preference")
    if turn.tool_iterations >= 5:
        signals.append("complex_workflow")
    if any(p in text for p in ("fixed", "workaround", "pitfall", "retry")):
        signals.append("technique_learned")
    return signals


def run_background_review(
    *,
    turns: list[TurnRecord],
    memory: MemoryStore,
    skills_dir: Path,
    usage: UsageTracker,
    origin_ctx: WriteOriginContext,
    review_memory: bool,
    review_skills: bool,
) -> list[str]:
    """
    Simulates agent/background_review._run_review_in_thread.

    Real Hermes forks AIAgent with tool whitelist {memory, skill_manage}.
    """
    actions: list[str] = []
    origin_ctx.set("background_review")
    try:
        for turn in turns:
            signals = detect_learning_signals(turn)
            if not signals:
                continue

            if review_memory and "user_preference" in signals:
                result = memory.tool_memory(
                    "add",
                    target="user",
                    content=f"User preference captured from turn: {turn.user_message[:80]}",
                )
                if result.get("success"):
                    actions.append("User profile updated")

            if review_skills and ("complex_workflow" in signals or "technique_learned" in signals):
                skill_name = "debugging-workflow"
                skill_dir = skills_dir / skill_name
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    content = (
                        "---\n"
                        f"name: {skill_name}\n"
                        "description: Class-level debugging workflow learned from experience.\n"
                        "---\n\n"
                        "# Debugging Workflow\n\n"
                        "1. Reproduce with minimal case\n"
                        "2. Check logs and metrics\n"
                        "3. Apply workaround and document pitfall\n"
                    )
                    skill_dir.mkdir(parents=True, exist_ok=True)
                    skill_md.write_text(content, encoding="utf-8")
                    if origin_ctx.is_background_review():
                        usage.mark_agent_created(skill_name)
                    actions.append(f"Skill '{skill_name}' created (agent-created)")
                else:
                    text = skill_md.read_text(encoding="utf-8")
                    if "pitfall" not in text.lower():
                        skill_md.write_text(
                            text + "\n\n## Pitfalls\n- Transient env errors are not durable rules.\n",
                            encoding="utf-8",
                        )
                        usage.bump_patch(skill_name)
                        actions.append(f"Skill '{skill_name}' patched")
    finally:
        origin_ctx.set("foreground")
    return actions


def should_trigger_review(nudge: NudgeState, *, has_memory_tool: bool, has_skill_tool: bool) -> tuple[bool, bool]:
    """Mirrors agent/turn_context.build_turn_context + agent/turn_finalizer.finalize_turn."""
    review_memory = False
    review_skills = False

    nudge.user_turn_count += 1
    if has_memory_tool and nudge.memory_nudge_interval > 0:
        nudge.turns_since_memory += 1
        if nudge.turns_since_memory >= nudge.memory_nudge_interval:
            review_memory = True
            nudge.turns_since_memory = 0

    if has_skill_tool and nudge.skill_nudge_interval > 0:
        if nudge.iters_since_skill >= nudge.skill_nudge_interval:
            review_skills = True
            nudge.iters_since_skill = 0

    return review_memory, review_skills
