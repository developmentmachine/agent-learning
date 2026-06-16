# Agent Evaluation Framework

This module provides a comprehensive evaluation framework for testing AI Agents, heavily inspired by industry best practices (including Anthropic, OpenAI, and enterprise implementations).

## Core Philosophy

Evaluating an Agent is fundamentally different from traditional software testing because of:
1. **Non-determinism**: The same prompt may yield different execution paths.
2. **Black-box drift**: Prompt tweaks or underlying model updates can cause silent regressions.
3. **Cascading errors**: A slight mistake in an early tool call amplifies downstream.

To address this, our evaluation framework relies on capturing the **Trace** (the full log of thoughts, tool calls, and outputs) and running it through a **Hybrid Evaluation System**.

## The Three Evaluators

There is no "silver bullet" for Agent evaluation. We use a combination of three evaluators:

1. **Deterministic Evaluator (The Hard Gate)**
   - **What it is**: Fast, cheap, and objective Python/Bash scripts or AST parsers.
   - **What it does**: Checks if a specific tool was called (`tool_call == 'mcp'`), if the correct parameters were used, or if a final file was successfully generated.
   - **Role**: Primary CI/CD gatekeeper.

2. **Rubric Evaluator / LLM-as-Judge (The Soft Gate)**
   - **What it is**: Using a fixed-version LLM with a strict Prompt + JSON Schema to grade qualitative metrics.
   - **What it does**: Evaluates reasoning paths, code style, explanation clarity, and intent alignment.
   - **Role**: Secondary gate. Handles what code cannot easily parse, but can be structurally described.

3. **Human Evaluator (The Gold Standard)**
   - **What it is**: Domain experts.
   - **What it does**: Calibrates the LLM-as-Judge, investigates 0% or 100% anomaly scores, and conducts Red Team security testing.
   - **Role**: Offline calibration, not part of the automated CI pipeline.

## Key Metrics

Instead of simple pass/fail, we measure probabilities over multiple trials (`Trial`):

- **pass@k**: The probability that the agent gets it right *at least once* in `k` trials. (Measures peak capability).
- **pass^k**: The probability that the agent gets it right *every single time* in `k` trials. (Measures stability and consistency).
- **Cost & Latency**: Tracking token usage and execution time per trace to establish performance baselines.

## Quick Start

See `evaluator.py` for a Python implementation of the Hybrid Evaluators.
