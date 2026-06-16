# Hermes Session Context Management Demo

This directory contains a demonstration of how advanced agents (like Hermes/Gemini CLI) manage multi-turn conversational context and pass it to Large Language Models.

## Overview
Agents need to maintain state across multiple interactions (User inputs, Model thoughts, Tool executions). They do this by maintaining a chronological list of `Messages` and managing the total token footprint (Context Window) to balance cost, performance, and memory retention.

## Files
- `session_manager.py`: Contains the `SessionManager` class. It demonstrates how to append role-based messages, estimate token usage, and automatically prune/truncate oversized tool outputs to protect the context window.
- `demo.py`: An executable script that simulates a multi-turn conversation. It shows how the full payload is continuously sent to the LLM and how the agent state is preserved.

## Usage
Run the demo to see how the context grows and how the LLM payload is assembled dynamically:

```bash
python demos/hermes-session-context-management/demo.py
```

## Further Reading
For a detailed explanation of the design patterns and how to implement them in your own agent, read the documentation at:
[`../../docs/hermes-session-context-management.md`](../../docs/hermes-session-context-management.md)
