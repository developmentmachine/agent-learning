---
name: repo-explore
description: Read-only codebase navigation — glob, search, and parallel reads before making edits.
version: 1.0.0
metadata:
  hermes:
    tags: [explore, read-only, navigation]
---

# Repo Explore

Use when you are unfamiliar with the repository or need to locate symbols, files, or patterns **before** editing.

## When to load

- User asks "where is X", "find usages of Y", "how does Z work"
- You are about to touch multiple modules and have not read them yet
- Broad refactors — map blast radius first

## Workflow

1. **Clarify target** — symbol name, feature area, or error string
2. **Glob by path** — `src/**/*.ts`, `**/*_test.go`, etc.
3. **Search by content** — definitions, imports, string literals from stack traces
4. **Read in parallel** — independent files in one turn
5. **Summarize map** — list paths + one-line role each; note entry points

## Rules

- **Read-only** — no writes, no install commands, no git mutations
- Prefer dedicated search/read tools over shell `grep`/`cat` when available
- Read call sites of changed symbols before proposing edits elsewhere
- Stop when you can name the 3–5 files that matter; do not read the whole repo

## Output

```markdown
## Findings
- `path/to/file` — role in one sentence

## Suggested next step
<single concrete action for the main agent>
```
