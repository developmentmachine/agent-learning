# Hermes Orchestration Loop Demo

This directory contains a demonstration of the **Core Reasoning Loop** and **Self-Correction** mechanisms, which are the fundamental "brains" of an autonomous Agent.

## Overview
A standalone Agent doesn't just call a tool and stop. it operates in a cycle:
1.  **Thought**: Analyze current state.
2.  **Action**: Decide which tool to call.
3.  **Observation**: Receive tool output or error.
4.  **Correction**: If an error occurred, re-plan and try again.

## Key Features in this Demo
- **The Orchestrator**: A Python implementation of the `while` loop that manages the lifecycle of a task.
- **Robust Error Handling**: Demonstrates how `Exceptions` from tools are caught and fed back to the LLM as `Observations`, enabling the agent to fix its own mistakes.
- **Trace Management**: Tracks the full history of thoughts and actions for debugging and evaluation.

## Usage
Run the demo to see an agent attempt a task, fail due to a missing file, correct itself, and finally provide a successful answer:

```bash
python demos/hermes-orchestration-loop/demo.py
```

## Further Reading
Read the theoretical foundation in the documentation:
[`../../docs/agent-core-reasoning-loop.md`](../../docs/agent-core-reasoning-loop.md)
