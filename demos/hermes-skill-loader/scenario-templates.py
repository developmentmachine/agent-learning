#!/usr/bin/env python3
"""
Walkthrough for Template A/B/C skills — no API key required.

Demonstrates categorized skill index (general / oncall / review) and
progressive disclosure: index → skill_view → references/.

Usage:
  python scenario-templates.py
  python scenario-templates.py --category oncall
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from skill_loader import HermesSkillLoader

ROOT = Path(__file__).resolve().parent
SKILLS_DIR = ROOT / "skills"
PROMPTS_DIR = ROOT / "prompts"

# (step title, tool name, tool args)
DEMO_STEPS: dict[str, list[tuple[str, str, dict[str, Any]]]] = {
    "coding": [
        ("List general/* skills", "skills_list", {"category": "general"}),
        ("Load repo-explore", "skill_view", {"name": "repo-explore"}),
        ("Load run-tests", "skill_view", {"name": "run-tests"}),
    ],
    "oncall": [
        ("List oncall/* skills", "skills_list", {"category": "oncall"}),
        ("Load incident-triage", "skill_view", {"name": "incident-triage"}),
        (
            "Tier-3 reference — three-part incident example",
            "skill_view",
            {
                "name": "incident-triage",
                "file_path": "references/example-gateway-503.md",
            },
        ),
    ],
    "review": [
        ("List review/* skills", "skills_list", {"category": "review"}),
        ("Load umbrella code-review", "skill_view", {"name": "code-review"}),
        ("Load security-review", "skill_view", {"name": "security-review"}),
    ],
}


def step(title: str, body: str) -> None:
    print()
    print("─" * 64)
    print(f"▶ {title}")
    print("─" * 64)
    print(body)


def format_tool_result(tool: str, args: dict[str, Any], result: str) -> str:
    parsed = json.loads(result)
    if tool == "skill_view" and parsed.get("success"):
        content = parsed.get("content", "")
        preview = content[:400].replace("\n", "\n  ")
        if len(content) > 400:
            preview += "\n  ..."
        return (
            f"{tool}({json.dumps(args, ensure_ascii=False)})\n"
            f"  lines={content.count(chr(10)) + 1}, chars={len(content)}\n"
            f"  preview:\n  {preview}"
        )
    if tool == "skills_list" and parsed.get("success"):
        names = [s["name"] for s in parsed.get("skills", [])]
        return f"{tool}({json.dumps(args, ensure_ascii=False)})\n  count={parsed.get('count')} names={names}"
    return f"{tool}({json.dumps(args, ensure_ascii=False)})\n  {result}"


def run_category(loader: HermesSkillLoader, category: str) -> None:
    prompt_file = PROMPTS_DIR / f"stable-{category}.md"
    step(f"Stable prompt snippet — Template {category}", prompt_file.read_text(encoding="utf-8"))
    for title, tool, args in DEMO_STEPS[category]:
        result = loader.dispatch_tool(tool, args)
        step(title, format_tool_result(tool, args, result))


def main() -> int:
    parser = argparse.ArgumentParser(description="Template A/B/C skill walkthrough")
    parser.add_argument(
        "--category",
        choices=["coding", "oncall", "review", "all"],
        default="all",
        help="Which template walkthrough to run",
    )
    args = parser.parse_args()

    loader = HermesSkillLoader(SKILLS_DIR, session_id="templates-demo")

    step("Full Tier-0 index (all categories)", loader.build_system_prompt_index())

    categories = ["coding", "oncall", "review"] if args.category == "all" else [args.category]
    for cat in categories:
        run_category(loader, cat)

    print()
    print("Done. Interactive: python demo.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
