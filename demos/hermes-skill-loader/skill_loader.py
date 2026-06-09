"""
Hermes-style Skill Loader — minimal runnable implementation.

Demonstrates Progressive Disclosure:
  Tier 0: metadata index (session start / skills_list)
  Tier 2: SKILL.md full content (skill_view)
  Tier 3: linked files (skill_view + file_path)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

LoadingMode = Literal["eager", "lazy"]

# ── Constants ─────────────────────────────────────────────────────────────

EXCLUDED_DIRS = {
    ".git",
    ".github",
    ".hub",
    ".archive",
    "node_modules",
    "__pycache__",
    ".venv",
}

MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_FRONTMATTER_SCAN = 4000

_SKILL_TEMPLATE_RE = re.compile(r"\$\{(HERMES_SKILL_DIR|HERMES_SESSION_ID)\}")
_INLINE_SHELL_RE = re.compile(r"!`([^`\n]+)`")
_INLINE_SHELL_MAX_OUTPUT = 4000

_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "you are now",
    "disregard your",
    "forget your instructions",
    "new instructions:",
    "system prompt:",
]


# ── Data models ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str
    category: str
    skill_dir: Path


@dataclass
class LoadedSkill:
    name: str
    content: str
    raw_content: str
    skill_dir: Path
    linked_files: dict[str, list[str]] = field(default_factory=dict)
    frontmatter: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillCmdInfo:
    name: str
    description: str
    skill_dir: Path


_SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


# ── Frontmatter parsing ───────────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    raw_fm = parts[1].strip()
    body = parts[2].lstrip("\n")
    frontmatter: dict[str, Any] = {}
    for line in raw_fm.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        frontmatter[key.strip()] = value.strip().strip("'\"")
    return frontmatter, body


def first_non_heading_line(body: str) -> str:
    for line in body.strip().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:MAX_DESCRIPTION_LENGTH]
    return ""


def normalize_slash_slug(name: str) -> str:
    slug = name.lower().replace(" ", "-").replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def has_traversal_component(path_str: str) -> bool:
    parts = Path(path_str).parts
    return ".." in parts or Path(path_str).is_absolute()


def validate_skill_name(name: str) -> str | None:
    if not name or not _SKILL_NAME_RE.match(name):
        return "Skill name must match [a-zA-Z0-9][a-zA-Z0-9_-]*"
    if has_traversal_component(name):
        return "Skill name cannot contain path traversal"
    return None


def security_scan_content(content: str) -> list[str]:
    lower = content.lower()
    return [p for p in _INJECTION_PATTERNS if p in lower]


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


# ── Discovery ─────────────────────────────────────────────────────────────

def iter_skill_index_files(skills_dir: Path, filename: str = "SKILL.md"):
    if not skills_dir.exists():
        return
    matches: list[Path] = []
    for root, dirs, files in os.walk(skills_dir, followlinks=True):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        if filename in files:
            matches.append(Path(root) / filename)
    for path in sorted(matches, key=lambda p: str(p.relative_to(skills_dir))):
        yield path


def infer_category(skill_md: Path, skills_root: Path) -> str:
    rel = skill_md.relative_to(skills_root)
    if len(rel.parts) > 2:
        return "/".join(rel.parts[:-2])
    return "general"


def find_all_skills_metadata(
    skills_dir: Path,
    *,
    disabled: set[str] | None = None,
) -> list[SkillMeta]:
    disabled = disabled or set()
    skills: list[SkillMeta] = []
    seen: set[str] = set()

    for skill_md in iter_skill_index_files(skills_dir):
        skill_dir = skill_md.parent
        try:
            content = skill_md.read_text(encoding="utf-8")[:MAX_FRONTMATTER_SCAN]
            fm, body = parse_frontmatter(content)
            name = str(fm.get("name", skill_dir.name))[:MAX_NAME_LENGTH]
            if name in seen or name in disabled:
                continue
            desc = str(fm.get("description", "")) or first_non_heading_line(body)
            if len(desc) > MAX_DESCRIPTION_LENGTH:
                desc = desc[: MAX_DESCRIPTION_LENGTH - 3] + "..."
            seen.add(name)
            skills.append(
                SkillMeta(
                    name=name,
                    description=desc,
                    category=infer_category(skill_md, skills_dir),
                    skill_dir=skill_dir,
                )
            )
        except (OSError, UnicodeDecodeError):
            continue
    return sorted(skills, key=lambda s: (s.category, s.name))


# ── Resolution & loading ────────────────────────────────────────────────────

def resolve_skill(
    skills_dir: Path,
    name: str,
) -> tuple[Path, Path] | None:
    if has_traversal_component(name):
        return None

    candidates: list[tuple[Path, Path]] = []
    seen: set[str] = set()

    def record(skill_dir: Path | None, skill_md: Path) -> None:
        key = str(skill_md.resolve())
        if key in seen:
            return
        seen.add(key)
        candidates.append((skill_dir or skill_md.parent, skill_md))

    direct = skills_dir / name
    if direct.is_dir() and (direct / "SKILL.md").exists():
        record(direct, direct / "SKILL.md")

    for skill_md in iter_skill_index_files(skills_dir):
        if skill_md.parent.name == name:
            record(skill_md.parent, skill_md)

    if len(candidates) > 1:
        raise AmbiguousSkillError(name, [str(md) for _, md in candidates])
    if not candidates:
        return None
    return candidates[0]


class AmbiguousSkillError(Exception):
    def __init__(self, name: str, matches: list[str]):
        self.name = name
        self.matches = matches
        super().__init__(f"Ambiguous skill '{name}': {matches}")


def scan_linked_files(skill_dir: Path) -> dict[str, list[str]]:
    linked: dict[str, list[str]] = {}
    for subdir in ("references", "templates", "scripts", "assets"):
        path = skill_dir / subdir
        if not path.exists():
            continue
        files = [
            str(f.relative_to(skill_dir))
            for f in sorted(path.rglob("*"))
            if f.is_file() and not f.is_symlink()
        ]
        if files:
            linked[subdir] = files
    return linked


def substitute_template_vars(
    content: str,
    skill_dir: Path | None,
    session_id: str | None,
) -> str:
    skill_dir_str = str(skill_dir) if skill_dir else None

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "HERMES_SKILL_DIR" and skill_dir_str:
            return skill_dir_str
        if token == "HERMES_SESSION_ID" and session_id:
            return session_id
        return match.group(0)

    return _SKILL_TEMPLATE_RE.sub(replace, content)


def expand_inline_shell(content: str, skill_dir: Path | None, timeout: int = 10) -> str:
    if "!`" not in content:
        return content

    def replace(match: re.Match[str]) -> str:
        cmd = match.group(1).strip()
        if not cmd:
            return ""
        try:
            completed = subprocess.run(
                ["bash", "-c", cmd],
                cwd=str(skill_dir) if skill_dir else None,
                capture_output=True,
                text=True,
                timeout=max(1, timeout),
                check=False,
                stdin=subprocess.DEVNULL,
            )
            output = (completed.stdout or completed.stderr or "").rstrip("\n")
        except Exception as exc:
            return f"[inline-shell error: {exc}]"
        if len(output) > _INLINE_SHELL_MAX_OUTPUT:
            output = output[:_INLINE_SHELL_MAX_OUTPUT] + "...[truncated]"
        return output

    return _INLINE_SHELL_RE.sub(replace, content)


def preprocess_skill_content(
    content: str,
    skill_dir: Path | None,
    session_id: str | None = None,
    *,
    template_vars: bool = True,
    inline_shell: bool = False,
) -> str:
    if template_vars:
        content = substitute_template_vars(content, skill_dir, session_id)
    if inline_shell:
        content = expand_inline_shell(content, skill_dir)
    return content


def load_skill_file(
    skill_md: Path,
    *,
    session_id: str | None = None,
    preprocess: bool = True,
    template_vars: bool = True,
    inline_shell: bool = False,
) -> LoadedSkill:
    raw = skill_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(raw)
    skill_dir = skill_md.parent
    rendered = body
    if preprocess:
        rendered = preprocess_skill_content(
            body,
            skill_dir,
            session_id,
            template_vars=template_vars,
            inline_shell=inline_shell,
        )
    return LoadedSkill(
        name=str(fm.get("name", skill_dir.name)),
        content=rendered.strip(),
        raw_content=raw,
        skill_dir=skill_dir,
        linked_files=scan_linked_files(skill_dir),
        frontmatter=fm,
    )


# ── HermesSkillLoader (main API) ──────────────────────────────────────────

class HermesSkillLoader:
    """
    Minimal Hermes-compatible skill loader.

    Usage:
        loader = HermesSkillLoader(Path("skills"))
        index = loader.build_system_prompt_index()
        result = loader.tool_skill_view("deploy-k8s")
    """

    def __init__(
        self,
        skills_dir: Path,
        *,
        disabled: set[str] | None = None,
        session_id: str | None = "demo-session-001",
        inline_shell: bool = False,
        loading_mode: LoadingMode = "eager",
    ):
        self.skills_dir = skills_dir.resolve()
        self.disabled = disabled or set()
        self.session_id = session_id
        self.inline_shell = inline_shell
        self.loading_mode = loading_mode
        self._index_cache: list[SkillMeta] | None = None
        self._slash_commands: dict[str, SkillCmdInfo] | None = None

    def refresh(self) -> None:
        self._index_cache = None
        self._slash_commands = None

    def scan_metadata(self) -> list[SkillMeta]:
        if self._index_cache is None:
            self._index_cache = find_all_skills_metadata(
                self.skills_dir, disabled=self.disabled
            )
        return list(self._index_cache)

    def build_system_prompt_index(self) -> str:
        if self.loading_mode == "lazy":
            return (
                "## Skills\n"
                "A skills catalog is available — call skills_list() when you think "
                "a specialized skill might help, then skill_view(name) to load it."
            )

        skills = self.scan_metadata()
        if not skills:
            return ""

        by_category: dict[str, list[SkillMeta]] = {}
        for meta in skills:
            by_category.setdefault(meta.category, []).append(meta)

        lines = [
            "## Skills (mandatory)",
            "If a skill matches your task, load it with skill_view(name).",
            "",
            "<available_skills>",
        ]
        for category in sorted(by_category):
            lines.append(f"  {category}:")
            for meta in by_category[category]:
                lines.append(f"    - {meta.name}: {meta.description}")
        lines.append("</available_skills>")
        return "\n".join(lines)

    def scan_skill_commands(self) -> dict[str, SkillCmdInfo]:
        if self._slash_commands is not None:
            return self._slash_commands

        commands: dict[str, SkillCmdInfo] = {}
        for meta in self.scan_metadata():
            slug = normalize_slash_slug(meta.name)
            if not slug:
                continue
            commands[f"/{slug}"] = SkillCmdInfo(
                name=meta.name,
                description=meta.description,
                skill_dir=meta.skill_dir,
            )
        self._slash_commands = commands
        return commands

    def tool_skills_list(self, category: str | None = None) -> str:
        skills = self.scan_metadata()
        if category:
            skills = [s for s in skills if s.category == category]
        payload = {
            "success": True,
            "skills": [
                {"name": s.name, "description": s.description, "category": s.category}
                for s in skills
            ],
            "count": len(skills),
            "hint": "Use skill_view(name) to load full SKILL.md content",
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def tool_skill_view(
        self,
        name: str,
        file_path: str | None = None,
        *,
        preprocess: bool = True,
    ) -> str:
        if has_traversal_component(name):
            return json.dumps({"success": False, "error": "Invalid skill name"})

        try:
            resolved = resolve_skill(self.skills_dir, name)
        except AmbiguousSkillError as exc:
            return json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "matches": exc.matches,
                },
                ensure_ascii=False,
                indent=2,
            )

        if resolved is None:
            available = [s.name for s in self.scan_metadata()[:10]]
            return json.dumps(
                {
                    "success": False,
                    "error": f"Skill '{name}' not found",
                    "available_skills": available,
                },
                ensure_ascii=False,
                indent=2,
            )

        skill_dir, skill_md = resolved

        if file_path:
            if has_traversal_component(file_path):
                return json.dumps({"success": False, "error": "Path traversal not allowed"})
            target = (skill_dir / file_path).resolve()
            try:
                target.relative_to(skill_dir.resolve())
            except ValueError:
                return json.dumps({"success": False, "error": "File outside skill directory"})
            if not target.exists():
                return json.dumps(
                    {
                        "success": False,
                        "error": f"File '{file_path}' not found",
                        "linked_files": scan_linked_files(skill_dir),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            return json.dumps(
                {
                    "success": True,
                    "name": name,
                    "file": file_path,
                    "content": target.read_text(encoding="utf-8"),
                },
                ensure_ascii=False,
                indent=2,
            )

        loaded = load_skill_file(
            skill_md,
            session_id=self.session_id,
            preprocess=preprocess,
            inline_shell=self.inline_shell,
        )

        lower = loaded.raw_content.lower()
        warnings = [p for p in _INJECTION_PATTERNS if p in lower]

        return json.dumps(
            {
                "success": True,
                "name": loaded.name,
                "content": loaded.content,
                "skill_dir": str(loaded.skill_dir),
                "linked_files": loaded.linked_files,
                "security_warnings": warnings or None,
                "hint": "Call skill_view(name, file_path=...) for linked files",
            },
            ensure_ascii=False,
            indent=2,
        )

    def build_slash_invocation_message(
        self,
        cmd_key: str,
        user_instruction: str = "",
    ) -> str | None:
        commands = self.scan_skill_commands()
        info = commands.get(cmd_key)
        if info is None:
            return None

        raw = self.tool_skill_view(str(info.skill_dir.name), preprocess=False)
        payload = json.loads(raw)
        if not payload.get("success"):
            return None

        # Hermes: skill_view(preprocess=False) + message builder does preprocessing
        content = preprocess_skill_content(
            payload["content"],
            Path(payload["skill_dir"]),
            self.session_id,
            inline_shell=self.inline_shell,
        )

        parts = [
            f'[IMPORTANT: User invoked "{info.name}" skill — follow its instructions.]',
            "",
            content,
            "",
            f"[Skill directory: {payload['skill_dir']}]",
        ]

        linked = payload.get("linked_files") or {}
        flat_files = [f for group in linked.values() for f in group]
        if flat_files:
            parts.append("")
            parts.append("[Supporting files — load with skill_view(name, file_path=...):]")
            for rel in flat_files:
                parts.append(f"  - {rel}")

        if user_instruction:
            parts.extend(["", f"User instruction: {user_instruction}"])

        return "\n".join(parts)

    def _skill_dir_for_name(self, name: str) -> Path | None:
        err = validate_skill_name(name)
        if err:
            return None
        return self.skills_dir / name

    def _read_skill_md(self, name: str) -> tuple[Path, str] | tuple[None, str]:
        skill_dir = self._skill_dir_for_name(name)
        if skill_dir is None:
            return None, "Invalid skill name"
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return None, f"Skill '{name}' not found"
        return skill_md, skill_md.read_text(encoding="utf-8")

    def tool_skill_manage(self, action: str, **kwargs: Any) -> str:
        """
        Agent procedural memory — create / patch / edit / delete skills on disk.

        Mirrors Hermes skill_manage: atomic write + security scan + cache refresh.
        """
        action = (action or "").strip().lower()
        name = (kwargs.get("name") or "").strip()

        if action in {"create", "patch", "edit", "delete", "write_file", "remove_file"}:
            if not name:
                return json.dumps({"success": False, "error": "Missing skill name"})
            name_err = validate_skill_name(name)
            if name_err:
                return json.dumps({"success": False, "error": name_err})

        try:
            if action == "create":
                content = kwargs.get("content") or ""
                if not content.strip():
                    return json.dumps({"success": False, "error": "content is required for create"})
                blocked = security_scan_content(content)
                if blocked:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Security scan blocked skill content",
                            "patterns": blocked,
                        }
                    )
                skill_dir = self.skills_dir / name
                if (skill_dir / "SKILL.md").exists():
                    return json.dumps({"success": False, "error": f"Skill '{name}' already exists"})
                atomic_write_text(skill_dir / "SKILL.md", content)
                self.refresh()
                return json.dumps(
                    {"success": True, "action": "create", "name": name, "path": str(skill_dir)}
                )

            if action == "patch":
                old_string = kwargs.get("old_string")
                new_string = kwargs.get("new_string")
                if old_string is None or new_string is None:
                    return json.dumps({"success": False, "error": "old_string and new_string required"})
                skill_md, content = self._read_skill_md(name)
                if skill_md is None:
                    return json.dumps({"success": False, "error": content})
                if old_string not in content:
                    return json.dumps({"success": False, "error": "old_string not found in SKILL.md"})
                updated = content.replace(old_string, new_string, 1)
                blocked = security_scan_content(updated)
                if blocked:
                    return json.dumps(
                        {"success": False, "error": "Security scan blocked patched content", "patterns": blocked}
                    )
                atomic_write_text(skill_md, updated)
                self.refresh()
                return json.dumps({"success": True, "action": "patch", "name": name})

            if action == "edit":
                content = kwargs.get("content") or ""
                if not content.strip():
                    return json.dumps({"success": False, "error": "content is required for edit"})
                skill_md, existing_or_err = self._read_skill_md(name)
                if skill_md is None:
                    return json.dumps({"success": False, "error": existing_or_err})
                blocked = security_scan_content(content)
                if blocked:
                    return json.dumps(
                        {"success": False, "error": "Security scan blocked edited content", "patterns": blocked}
                    )
                atomic_write_text(skill_md, content)
                self.refresh()
                return json.dumps({"success": True, "action": "edit", "name": name})

            if action == "delete":
                skill_dir = self._skill_dir_for_name(name)
                if skill_dir is None or not skill_dir.exists():
                    return json.dumps({"success": False, "error": f"Skill '{name}' not found"})
                shutil.rmtree(skill_dir)
                self.refresh()
                return json.dumps({"success": True, "action": "delete", "name": name})

            if action == "write_file":
                file_path = (kwargs.get("file_path") or "").strip()
                file_content = kwargs.get("file_content")
                if not file_path or file_content is None:
                    return json.dumps({"success": False, "error": "file_path and file_content required"})
                if has_traversal_component(file_path):
                    return json.dumps({"success": False, "error": "Invalid file_path"})
                skill_dir = self._skill_dir_for_name(name)
                if skill_dir is None or not (skill_dir / "SKILL.md").exists():
                    return json.dumps({"success": False, "error": f"Skill '{name}' not found"})
                blocked = security_scan_content(str(file_content))
                if blocked:
                    return json.dumps(
                        {"success": False, "error": "Security scan blocked file content", "patterns": blocked}
                    )
                target = (skill_dir / file_path).resolve()
                try:
                    target.relative_to(skill_dir.resolve())
                except ValueError:
                    return json.dumps({"success": False, "error": "file_path escapes skill directory"})
                atomic_write_text(target, str(file_content))
                self.refresh()
                return json.dumps({"success": True, "action": "write_file", "name": name, "file_path": file_path})

            if action == "remove_file":
                file_path = (kwargs.get("file_path") or "").strip()
                if not file_path:
                    return json.dumps({"success": False, "error": "file_path required"})
                if has_traversal_component(file_path):
                    return json.dumps({"success": False, "error": "Invalid file_path"})
                skill_dir = self._skill_dir_for_name(name)
                if skill_dir is None:
                    return json.dumps({"success": False, "error": f"Skill '{name}' not found"})
                target = skill_dir / file_path
                if not target.exists():
                    return json.dumps({"success": False, "error": f"File '{file_path}' not found"})
                target.unlink()
                self.refresh()
                return json.dumps({"success": True, "action": "remove_file", "name": name, "file_path": file_path})

            return json.dumps(
                {
                    "success": False,
                    "error": f"Unknown action '{action}'",
                    "supported": ["create", "patch", "edit", "delete", "write_file", "remove_file"],
                }
            )
        except OSError as exc:
            return json.dumps({"success": False, "error": str(exc)})

    def dispatch_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "skills_list":
            return self.tool_skills_list(args.get("category"))
        if tool_name == "skill_view":
            return self.tool_skill_view(
                args["name"],
                args.get("file_path"),
            )
        if tool_name == "skill_manage":
            return self.tool_skill_manage(
                args.get("action", ""),
                name=args.get("name"),
                content=args.get("content"),
                old_string=args.get("old_string"),
                new_string=args.get("new_string"),
                file_path=args.get("file_path"),
                file_content=args.get("file_content"),
            )
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"})


# ── Mock agent loop (for demo) ────────────────────────────────────────────

ToolCall = tuple[str, dict[str, Any]]


def mock_agent_decide(user_text: str, loader: HermesSkillLoader) -> list[ToolCall] | str:
    """
    Extremely naive 'agent' for demo purposes.
    Real Hermes uses an LLM to decide tool calls.
    """
    lower = user_text.lower()
    if user_text.startswith("/"):
        return user_text  # handled as slash command, not tool

    if "list" in lower and "skill" in lower:
        return [("skills_list", {})]

    if "deploy" in lower or "k8s" in lower or "kubernetes" in lower:
        return [("skill_view", {"name": "deploy-k8s"})]

    if "review" in lower and "code" in lower:
        return [("skill_view", {"name": "code-review"})]

    if "reference" in lower or "checklist" in lower:
        return [("skill_view", {"name": "deploy-k8s", "file_path": "references/checklist.md"})]

    if "save skill" in lower or "create skill" in lower:
        return [
            (
                "skill_manage",
                {
                    "action": "create",
                    "name": "api-migration",
                    "content": (
                        "---\n"
                        "name: api-migration\n"
                        "description: Migrate REST handlers from v1 to v2 with compatibility shims.\n"
                        "---\n\n"
                        "# API v1 → v2 Migration\n\n"
                        "1. Add v2 route alongside v1\n"
                        "2. Dual-write for 2 weeks\n"
                        "3. Switch reads to v2\n"
                        "4. Deprecate v1 with sunset header\n"
                    ),
                },
            )
        ]

    if "patch skill" in lower or "update skill" in lower:
        return [
            (
                "skill_manage",
                {
                    "action": "patch",
                    "name": "api-migration",
                    "old_string": "Dual-write for 2 weeks",
                    "new_string": "Dual-write for 4 weeks (production soak)",
                },
            )
        ]

    return (
        "I don't know which skill to load. Try:\n"
        "  - list skills\n"
        "  - deploy to k8s\n"
        "  - /deploy-k8s\n"
        "  - save skill (creates api-migration demo skill)\n"
        "  - patch skill (updates api-migration)"
    )


def run_agent_turn(loader: HermesSkillLoader, user_text: str) -> str:
    if user_text.startswith("/"):
        cmd = user_text.split()[0]
        rest = user_text[len(cmd) :].strip()
        msg = loader.build_slash_invocation_message(cmd, rest)
        if msg is None:
            return f"Unknown slash command: {cmd}"
        return f"=== Slash command loaded ===\n\n{msg}"

    decision = mock_agent_decide(user_text, loader)
    if isinstance(decision, str):
        return decision

    outputs: list[str] = []
    for tool_name, args in decision:
        result = loader.dispatch_tool(tool_name, args)
        outputs.append(f"=== Tool: {tool_name}({json.dumps(args, ensure_ascii=False)}) ===\n{result}")
    return "\n\n".join(outputs)
