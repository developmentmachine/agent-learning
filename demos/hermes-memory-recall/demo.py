#!/usr/bin/env python3
"""
Hermes memory recall — three-path walkthrough (no API key).

Run:
  cd demos/hermes-memory-recall
  python demo.py

Paths demonstrated:
  A. Declarative memory → system prompt volatile tier (frozen at session start)
  B. session_search     → tool message in messages[] (on-demand)
  C. skill_view         → tool message in messages[] (progressive disclosure)
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from memory_recall import (
    AgentSession,
    MemoryStore,
    SessionDB,
    build_system_prompt,
    format_recall_for_model,
    session_search,
)

ROOT = Path(__file__).resolve().parent
SANDBOX = ROOT / "_sandbox"
MEM_DIR = SANDBOX / "memories"
DB_PATH = SANDBOX / "state.db"

sys.path.insert(0, str(ROOT.parent / "hermes-skill-loader"))
from skill_loader import HermesSkillLoader  # noqa: E402

STABLE_IDENTITY = (
    "You are a helpful coding agent.\n"
    "When the user references past conversations, call session_search before asking them to repeat."
)


def banner(title: str) -> None:
    print()
    print("─" * 64)
    print(f"▶ {title}")
    print("─" * 64)


def reset_sandbox() -> None:
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True)
    src_skill = ROOT.parent / "hermes-skill-loader" / "skills" / "deploy-k8s"
    shutil.copytree(src_skill, SANDBOX / "skills" / "deploy-k8s")


def main() -> int:
    reset_sandbox()

    # ── Seed persistent memory + past session DB ────────────────────────
    mem = MemoryStore()
    mem.memory_entries = ["Project uses Python 3.12 and uv for scripts."]
    mem.user_entries = ["User prefers concise replies, no emoji."]
    mem.save(MEM_DIR)

    db = SessionDB(DB_PATH)
    db.seed_session(
        "sess-last-week",
        "k8s rollout debug",
        [
            ("user", "Last week we fixed the canary rollout — remember the maxUnavailable=0 trick?"),
            ("assistant", "Yes: set maxUnavailable=0 and maxSurge=1 so old pods stay until new ones pass probes."),
            ("user", "Great, apply the same pattern next time."),
        ],
    )

    loader = HermesSkillLoader(SANDBOX / "skills", session_id="recall-demo-001")

    # ══════════════════════════════════════════════════════════════════════
    banner("Path A — Declarative memory: frozen snapshot → system prompt")
    mem.load_from_disk(MEM_DIR)
    system = build_system_prompt(stable=STABLE_IDENTITY, memory_store=mem)
    session = AgentSession(system_prompt=system)

    print("Volatile tier injected at session start (from _system_prompt_snapshot):")
    print("─" * 40)
    for line in system.splitlines():
        if line.startswith("═") or "MEMORY" in line or "USER PROFILE" in line or "Python" in line or "concise" in line:
            print(line)
    print()
    print("Upstream: agent/system_prompt.py :: build_system_prompt_parts → volatile_parts")
    print("Upstream: tools/memory_tool.py :: format_for_system_prompt() returns FROZEN snapshot")

    # Mid-session write does NOT change cached system prompt
    mem.tool_memory("add", target="user", content="User asked about memory recall today.")
    mem.save(MEM_DIR)
    print()
    print("After mid-session memory(add):")
    print(f"  live entries count: {len(mem.user_entries)}")
    print(f"  system prompt still shows {len(mem.format_for_system_prompt('user') or '')} chars (unchanged snapshot)")

    # ══════════════════════════════════════════════════════════════════════
    banner("Path B — session_search: recall → tool message (NOT system prompt)")
    session.add_user("What was that k8s trick we discussed last week?")
    raw = session_search(db, query="canary maxUnavailable", current_session_id="recall-demo-001", limit=2)
    trimmed = format_recall_for_model(raw)
    session.inject_tool_recall("session_search", "call_search_1", trimmed)

    print("User turn added. Agent calls session_search → result injected as role=tool:")
    print(json.dumps(json.loads(trimmed), indent=2, ensure_ascii=False)[:900], "...")
    print()
    print("Upstream: tools/session_search_tool.py :: _discover → JSON string")
    print("Injection site: messages[] tool role, NOT system prompt")

    # ══════════════════════════════════════════════════════════════════════
    banner("Path C — skill_view: procedural memory → tool message")
    skill_body = loader.tool_skill_view("deploy-k8s")
    session.inject_tool_recall("skill_view", "call_skill_1", skill_body[:1200])
    print("skill_view payload (truncated):")
    print(skill_body[:500], "...")
    print()
    print("Upstream: tools/skills_tool.py :: skill_view → markdown in tool result")
    print("Tier-0 index stays in stable system prompt; full SKILL.md only after tool call")

    # ══════════════════════════════════════════════════════════════════════
    banner("Full API payload shape (what the model actually sees)")
    payload = session.build_api_payload()
    for i, msg in enumerate(payload):
        role = msg["role"]
        content = msg["content"]
        preview = content[:120].replace("\n", " ") + ("…" if len(content) > 120 else "")
        print(f"  [{i}] {role:10} {preview}")

    # ══════════════════════════════════════════════════════════════════════
    banner("Post-compression rebuild: memory snapshot refreshes")
    session.after_compression_rebuild(mem, MEM_DIR, STABLE_IDENTITY)
    user_block = mem.format_for_system_prompt("user") or ""
    print("After invalidate_system_prompt() + load_from_disk():")
    print("  new mid-session entry now visible in system prompt:")
    print(" ", "memory recall" in user_block)
    print()
    print("Upstream: agent/system_prompt.py :: invalidate_system_prompt()")

    db.close()
    print()
    print("═" * 64)
    print("Demo complete. Key rule:")
    print("  curated facts  → system prompt (session-start snapshot)")
    print("  past transcripts / skill bodies → tool messages (on-demand)")
    print("═" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
