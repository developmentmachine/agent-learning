#!/usr/bin/env python3
"""
Run the Hermes-style skill loader demo.

Examples:
  python demo.py                              # interactive REPL
  python demo.py --show-index                 # Tier-0 system prompt index
  python demo.py --loading lazy --show-index  # lazy mode (no index)
  python demo.py --turn "list skills"
  python demo.py --turn "save skill"          # skill_manage create demo
  python scenario.py                          # full scripted walkthrough
  python scenario-templates.py                # Template A/B/C skills walkthrough
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skill_loader import HermesSkillLoader, run_agent_turn

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def print_banner() -> None:
    print("=" * 60)
    print("Hermes Skill Loader — Minimal Demo")
    print("=" * 60)
    print(f"Skills directory: {SKILLS_DIR}")
    print()
    print("Try these inputs:")
    print("  list skills | list skills oncall | list skills review")
    print("  explore repo | run tests | debug build")
    print("  incident alert | incident example gateway 503")
    print("  review pr | security review | test gap")
    print("  help me deploy to k8s | /deploy-k8s")
    print("  save skill | patch skill")
    print("  quit")
    print()
    print("Walkthroughs (no API key):")
    print("  python scenario.py")
    print("  python scenario-templates.py")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes skill loader demo")
    parser.add_argument("--show-index", action="store_true", help="Print Tier-0 index")
    parser.add_argument("--turn", type=str, help="Run a single user turn")
    parser.add_argument("--inline-shell", action="store_true", help="Enable !`cmd` expansion")
    parser.add_argument(
        "--loading",
        choices=["eager", "lazy"],
        default="eager",
        help="eager=index in system prompt; lazy=skills_list on demand",
    )
    args = parser.parse_args()

    loader = HermesSkillLoader(
        SKILLS_DIR,
        inline_shell=args.inline_shell,
        loading_mode=args.loading,
    )

    if args.show_index:
        print(f"[loading_mode={args.loading}]")
        print(loader.build_system_prompt_index())
        print()
        print("=== Slash commands ===")
        for cmd, info in sorted(loader.scan_skill_commands().items()):
            print(f"  {cmd:20}  {info.name}")
        return 0

    if args.turn:
        print(run_agent_turn(loader, args.turn))
        return 0

    print_banner()
    print(f"=== Session Start [{args.loading}] ===")
    print(loader.build_system_prompt_index())
    print()

    while True:
        try:
            user_text = input("user> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            continue
        if user_text.lower() in {"quit", "exit", "q"}:
            break
        print()
        print(run_agent_turn(loader, user_text))
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
