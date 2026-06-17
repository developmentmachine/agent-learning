# Agent Guardrails & Safety Demo

This directory contains a demonstration of the **Guardrails** framework, which ensures that an autonomous Agent operates safely, ethically, and within budget.

## Overview
Guardrails are the security and operational layer that wraps around the Agent. This demo covers the three key stages of safety:
1.  **Input Guardrails**: Blocking prompt injections and malicious instructions.
2.  **Execution Guardrails**: Implementing **Human-in-the-Loop (HITL)** for sensitive tools (e.g., deleting data) and enforcing resource quotas (Token limits).
3.  **Output Guardrails**: Filtering sensitive data or PII before it reaches the user.

## Files
- `guardrails.py`: A flexible Python implementation of an `AgentGuardrails` system.
- `demo.py`: A script simulating multiple safety scenarios, including a prompt injection attack and a destructive action that requires manual approval.

## Usage
Run the demo and interact with the CLI to approve or reject sensitive actions:

```bash
python demos/agent-guardrails/demo.py
```

## Further Reading
For the full theoretical background on why guardrails are the "brakes" of an AI Agent, check:
[`../../docs/agent-guardrails.md`](../../docs/agent-guardrails.md)
