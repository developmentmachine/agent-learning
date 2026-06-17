# Agent Observability & Tracing Demo

This directory contains a demonstration of **Enterprise-grade Observability**, which is essential for monitoring, debugging, and auditing AI Agents in production.

## Overview
In a production environment, an Agent is not a black box. You need to see exactly what happened inside every execution. This demo implements a **Tracing System** that captures:
1.  **Trace ID**: A unique identifier for every user request.
2.  **Spans**: Individual units of work (Memory retrieval, LLM calls, Tool actions).
3.  **Metadata**: Detailed info like latency, token counts, and model names.
4.  **Audit Logs**: Structured JSON reports for post-mortem analysis.

## Files
- `tracer.py`: A core implementation of an `AgentTracer` that collects structured data during execution.
- `demo.py`: A script that simulates a complex debugging task and generates a full audit trace.

## Usage
Run the demo to generate a structured execution trace:

```bash
python demos/agent-observability/demo.py
```

Check the generated `agent_execution_trace.json` to see how the "inner thoughts" and metrics of the Agent are recorded.

## Further Reading
Read more about the importance of observability in enterprise engineering:
[`../../docs/agent-observability.md`](../../docs/agent-observability.md)
