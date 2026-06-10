"""
Hermes memory recall — minimal runnable simulation.

Mirrors three upstream recall paths:
  1. Declarative memory  — tools/memory_tool.py :: frozen snapshot → system prompt volatile tier
  2. Session search      — tools/session_search_tool.py :: FTS5 → tool result in messages[]
  3. Procedural memory   — tools/skills_tool.py :: skill_view → tool result in messages[]

Injection rules (from agent/system_prompt.py):
  - MEMORY/USER blocks enter system prompt ONCE per session (frozen snapshot).
  - session_search / skill_view enter the session as standard tool-role messages.
  - Mid-session memory writes do NOT mutate the cached system prompt.
  - After context compression, invalidate_system_prompt() reloads memory from disk.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]

ENTRY_DELIMITER = "\n§\n"
MEMORY_LIMIT = 2200
USER_LIMIT = 1375


# ── 1. Declarative memory (frozen snapshot) ───────────────────────────────


@dataclass
class MemoryStore:
    """Subset of tools/memory_tool.py :: MemoryStore."""

    memory_entries: list[str] = field(default_factory=list)
    user_entries: list[str] = field(default_factory=list)
    memory_limit: int = MEMORY_LIMIT
    user_limit: int = USER_LIMIT
    _system_prompt_snapshot: dict[str, str] = field(default_factory=dict)

    def load_from_disk(self, mem_dir: Path) -> None:
        mem_dir.mkdir(parents=True, exist_ok=True)
        self.memory_entries = self._read_file(mem_dir / "MEMORY.md")
        self.user_entries = self._read_file(mem_dir / "USER.md")
        self._system_prompt_snapshot = {
            "memory": self._render_block("memory", self.memory_entries),
            "user": self._render_block("user", self.user_entries),
        }

    def format_for_system_prompt(self, target: str) -> str | None:
        block = self._system_prompt_snapshot.get(target, "")
        return block or None

    def tool_memory(self, action: str, *, target: str = "memory", content: str = "") -> dict[str, Any]:
        entries = self.memory_entries if target == "memory" else self.user_entries
        if action == "add":
            if content in entries:
                return {"success": True, "message": "duplicate", "entries": entries}
            entries.append(content)
            return {"success": True, "message": "added", "entries": list(entries)}
        return {"success": False, "error": f"unsupported action {action}"}

    def save(self, mem_dir: Path) -> None:
        mem_dir.mkdir(parents=True, exist_ok=True)
        (mem_dir / "MEMORY.md").write_text(ENTRY_DELIMITER.join(self.memory_entries), encoding="utf-8")
        (mem_dir / "USER.md").write_text(ENTRY_DELIMITER.join(self.user_entries), encoding="utf-8")

    @staticmethod
    def _read_file(path: Path) -> list[str]:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8").strip()
        return [e.strip() for e in text.split(ENTRY_DELIMITER) if e.strip()] if text else []

    def _render_block(self, target: str, entries: list[str]) -> str:
        if not entries:
            return ""
        limit = self.user_limit if target == "user" else self.memory_limit
        content = ENTRY_DELIMITER.join(entries)
        header = (
            "USER PROFILE (who the user is)"
            if target == "user"
            else "MEMORY (your personal notes)"
        )
        pct = min(100, int(len(content) / limit * 100)) if limit else 0
        sep = "═" * 46
        return f"{sep}\n{header} [{pct}% — {len(content):,}/{limit:,} chars]\n{sep}\n{content}"


def build_system_prompt(
    *,
    stable: str,
    memory_store: MemoryStore | None,
    memory_enabled: bool = True,
    user_profile_enabled: bool = True,
) -> str:
    """Mirrors agent/system_prompt.py :: build_system_prompt (three tiers)."""
    parts = [stable.strip()]
    volatile: list[str] = []
    if memory_store and memory_enabled:
        mem = memory_store.format_for_system_prompt("memory")
        if mem:
            volatile.append(mem)
    if memory_store and user_profile_enabled:
        user = memory_store.format_for_system_prompt("user")
        if user:
            volatile.append(user)
    volatile.append("Conversation started: Wednesday, June 10, 2026")
    parts.append("\n\n".join(volatile))
    return "\n\n".join(p for p in parts if p)


def invalidate_system_prompt(memory_store: MemoryStore, mem_dir: Path) -> None:
    """Mirrors agent/system_prompt.py :: invalidate_system_prompt (post-compression)."""
    memory_store.load_from_disk(mem_dir)


# ── 2. Session search (on-demand → tool messages) ─────────────────────────


@dataclass
class StoredMessage:
    id: int
    session_id: str
    role: str
    content: str


class SessionDB:
    """Tiny SQLite + FTS5 stand-in for hermes_state.SessionDB."""

    def __init__(self, path: Path):
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        c = self._conn
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                started_at REAL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
            """
        )
        c.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                role,
                session_id UNINDEXED,
                content='messages',
                content_rowid='id'
            )
            """
        )
        c.commit()

    def seed_session(self, session_id: str, title: str, messages: list[tuple[str, str]]) -> None:
        c = self._conn
        c.execute("INSERT OR REPLACE INTO sessions(id, title, started_at) VALUES (?, ?, ?)", (session_id, title, 1.0))
        c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        for role, content in messages:
            c.execute("INSERT INTO messages(session_id, role, content) VALUES (?, ?, ?)", (session_id, role, content))
        c.execute("INSERT INTO messages_fts(rowid, content, role, session_id) SELECT id, content, role, session_id FROM messages WHERE session_id = ?", (session_id,))
        c.commit()

    def search_messages(self, query: str, *, limit: int = 3, exclude_session: str | None = None) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT m.id, m.session_id, m.role, m.content,
                   snippet(messages_fts, 0, '【', '】', '…', 20) AS snippet
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            WHERE messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit * 5),
        ).fetchall()
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for row in rows:
            sid = row["session_id"]
            if exclude_session and sid == exclude_session:
                continue
            if sid in seen:
                continue
            seen.add(sid)
            window = self.get_messages_around(sid, row["id"], window=2)
            results.append(
                {
                    "session_id": sid,
                    "match_message_id": row["id"],
                    "matched_role": row["role"],
                    "snippet": row["snippet"],
                    "window": window,
                }
            )
            if len(results) >= limit:
                break
        return results

    def get_messages_around(self, session_id: str, msg_id: int, *, window: int = 2) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, role, content FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if msg_id not in ids:
            return []
        idx = ids.index(msg_id)
        lo = max(0, idx - window)
        hi = min(len(rows), idx + window + 1)
        out = []
        for r in rows[lo:hi]:
            entry = {"id": r["id"], "role": r["role"], "content": r["content"]}
            if r["id"] == msg_id:
                entry["anchor"] = True
            out.append(entry)
        return out

    def close(self) -> None:
        self._conn.close()


def session_search(
    db: SessionDB,
    *,
    query: str = "",
    session_id: str | None = None,
    around_message_id: int | None = None,
    current_session_id: str | None = None,
    limit: int = 3,
) -> str:
    """Mirrors tools/session_search_tool.py mode inference."""
    if session_id and around_message_id is not None:
        if current_session_id and session_id == current_session_id:
            return json.dumps({"success": False, "error": "scroll rejected: same session lineage"})
        window = db.get_messages_around(session_id, around_message_id, window=5)
        return json.dumps({"success": True, "mode": "scroll", "messages": window}, ensure_ascii=False)

    if query:
        hits = db.search_messages(query, limit=limit, exclude_session=current_session_id)
        return json.dumps({"success": True, "mode": "discover", "query": query, "results": hits}, ensure_ascii=False)

    return json.dumps({"success": True, "mode": "browse", "message": "pass query= to search"})


# ── 3. Session message assembly (correct injection) ─────────────────────


@dataclass
class ChatMessage:
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class AgentSession:
    """
    Shows how Hermes assembles a turn:
      system prompt cached once; recalled fragments arrive via tool messages.
    """

    system_prompt: str
    messages: list[ChatMessage] = field(default_factory=list)
    _cached_system_prompt: str | None = None

    def __post_init__(self) -> None:
        self._cached_system_prompt = self.system_prompt

    @property
    def cached_system_prompt(self) -> str:
        return self._cached_system_prompt or self.system_prompt

    def add_user(self, text: str) -> None:
        self.messages.append(ChatMessage(role="user", content=text))

    def add_assistant(self, text: str) -> None:
        self.messages.append(ChatMessage(role="assistant", content=text))

    def inject_tool_recall(self, tool_name: str, tool_call_id: str, payload: str) -> None:
        """
        Standard OpenAI-style tool round-trip.
        Recalled content NEVER goes into system prompt mid-session.
        """
        self.messages.append(
            ChatMessage(
                role="assistant",
                content="",
                # In real Hermes this is tool_calls[]; we keep a readable trace.
            )
        )
        self.messages[-1].content = f"[tool_call {tool_name} id={tool_call_id}]"
        self.messages.append(
            ChatMessage(role="tool", name=tool_name, tool_call_id=tool_call_id, content=payload)
        )

    def build_api_payload(self) -> list[dict[str, Any]]:
        return [{"role": "system", "content": self.cached_system_prompt}, *[m.to_dict() for m in self.messages]]

    def after_compression_rebuild(self, memory_store: MemoryStore, mem_dir: Path, stable: str) -> None:
        invalidate_system_prompt(memory_store, mem_dir)
        self._cached_system_prompt = build_system_prompt(stable=stable, memory_store=memory_store)


def format_recall_for_model(search_json: str, *, max_chars: int = 4000) -> str:
    """Trim oversized session_search payloads before injection."""
    if len(search_json) <= max_chars:
        return search_json
    data = json.loads(search_json)
    data["truncated"] = True
    data["message"] = f"Payload trimmed to {max_chars} chars; use scroll mode for more."
    compact = json.dumps(data, ensure_ascii=False)
    return compact[:max_chars]
