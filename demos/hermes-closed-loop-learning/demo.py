#!/usr/bin/env python3
"""
Hermes closed-loop learning — end-to-end walkthrough (no API key).

Run:
  cd demos/hermes-closed-loop-learning
  python demo.py

Simulates:
  Session 1 → agent works → post-turn background review → memory + skill evolve
  Session 2 → frozen memory snapshot injected → evolved skill loaded
  Curator   → stale/archive transitions on idle agent-created skills
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from learning_loop import (
    MemoryStore,
    NudgeState,
    TurnRecord,
    UsageTracker,
    WriteOriginContext,
    run_background_review,
    should_trigger_review,
)

# Reuse skill loader from sibling demo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hermes-skill-loader"))
from skill_loader import HermesSkillLoader  # noqa: E402

ROOT = Path(__file__).resolve().parent
SANDBOX = ROOT / "_sandbox"
MEM_DIR = SANDBOX / "memories"
SKILLS_DIR = SANDBOX / "skills"


def banner(title: str) -> None:
    print()
    print("─" * 64)
    print(f"▶ {title}")
    print("─" * 64)


def reset_sandbox() -> None:
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SKILLS_DIR.mkdir(parents=True)
    MEM_DIR.mkdir(parents=True)
    # Seed one bundled-style skill
    src = Path(__file__).resolve().parent.parent / "hermes-skill-loader" / "skills" / "deploy-k8s"
    shutil.copytree(src, SKILLS_DIR / "deploy-k8s")


def main() -> int:
    reset_sandbox()

    memory = MemoryStore()
    memory.load(MEM_DIR)
    usage = UsageTracker(SKILLS_DIR)
    origin = WriteOriginContext()
    nudge = NudgeState(memory_nudge_interval=1, skill_nudge_interval=3)
    loader = HermesSkillLoader(SKILLS_DIR, session_id="closed-loop-001")
    pending_turns: list[TurnRecord] = []

    banner("Phase 0 — Session start: frozen memory snapshot (empty)")
    print(memory.system_prompt_block() or "(no memory yet)")
    print()
    print("System prompt also includes skill index:")
    print(loader.build_system_prompt_index()[:400], "...")

    banner("Phase 1 — Foreground turn: user task with preference signal")
    turn1 = TurnRecord(
        user_message="Deploy my API to k8s — and please stop giving verbose explanations",
        assistant_summary="Used deploy-k8s skill, applied canary rollout, deployment succeeded after 6 tool calls",
        tool_iterations=6,
    )
    pending_turns.append(turn1)
    nudge.iters_since_skill = 6  # no skill_manage this turn → triggers skill review

    review_mem, review_skill = should_trigger_review(nudge, has_memory_tool=True, has_skill_tool=True)
    print(f"Post-turn nudge flags: review_memory={review_mem}, review_skills={review_skill}")

    banner("Phase 2 — Background review fork (daemon thread, tools: memory + skill_manage only)")
    actions = run_background_review(
        turns=pending_turns,
        memory=memory,
        skills_dir=SKILLS_DIR,
        usage=usage,
        origin_ctx=origin,
        review_memory=review_mem,
        review_skills=review_skill,
    )
    memory.save(MEM_DIR)
    pending_turns.clear()
    print("Self-improvement review:", " · ".join(actions) if actions else "Nothing to save.")

    banner("Phase 3 — Disk state after review")
    print("USER.md:")
    print((MEM_DIR / "USER.md").read_text(encoding="utf-8") or "(empty)")
    print()
    skill_path = SKILLS_DIR / "debugging-workflow" / "SKILL.md"
    if skill_path.exists():
        print("Agent-created skill (marked in .usage.json):")
        print(skill_path.read_text(encoding="utf-8")[:500])
        print("...")
        print("usage record:", usage._data.get("debugging-workflow"))

    banner("Phase 4 — NEW session: memory snapshot refreshes, skill index updates")
    memory2 = MemoryStore()
    memory2.load(MEM_DIR)
    loader.refresh()
    print(memory2.system_prompt_block())
    print()
    print("Updated skill index excerpt:")
    for line in loader.build_system_prompt_index().splitlines():
        if "debugging" in line or "deploy" in line:
            print(" ", line)

    banner("Phase 5 — Agent loads evolved procedural memory on demand")
    result = loader.tool_skill_view("debugging-workflow")
    usage.bump_view("debugging-workflow")
    print(result[:600], "...")

    banner("Phase 6 — Curator deterministic lifecycle (no LLM)")
    # Simulate 95 days idle on agent-created skill
    rec = usage._data["debugging-workflow"]
    old_ts = (datetime.now(timezone.utc) - timedelta(days=95)).isoformat()
    rec.last_viewed_at = old_ts
    rec.last_patched_at = old_ts
    rec.created_at = old_ts
    usage.save()

    events = usage.apply_lifecycle(
        ["debugging-workflow"],
        stale_after_days=30,
        archive_after_days=90,
        skills_dir=SKILLS_DIR,
    )
    print("Curator auto-transitions:", events or "(none)")
    print("Archived exists:", (SKILLS_DIR / ".archive" / "debugging-workflow").exists())

    print()
    print("═" * 64)
    print("Demo complete. Sandbox:", SANDBOX)
    print("Compare with Hermes upstream:")
    print("  agent/background_review.py  — post-turn fork")
    print("  agent/turn_finalizer.py     — nudge trigger")
    print("  tools/memory_tool.py        — declarative memory")
    print("  tools/skill_manager_tool.py   — procedural memory")
    print("  tools/skill_usage.py        — curator telemetry")
    print("  agent/curator.py            — lifecycle + LLM review")
    print("═" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
