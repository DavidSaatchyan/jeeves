# ADR-003: Agent Coordination Model

**Status:** accepted
**Date:** 2026-06-10
**Author:** OpenFlo

## Context

OpenFlo needs to coordinate multiple agents. Research (T1.1) confirmed OpenCode has no Agent Teams, SendMessage, or shared memory between tasks.

Options:
1. **Coordinator-Style** — swarm agent orchestrates sub-agents via `task` tool, passing context through prompts
2. **SendMessage-Style** — agents communicate directly (requires infrastructure OpenCode doesn't have)
3. **MCP-Bus-Style** — all coordination through MCP memory (agents read/write tasks to memory)

## Decision

Use **Coordinator-Style** (option 1), with MCP as persistent memory layer.

How it works:
1. `swarm` agent receives user request
2. `swarm` creates a plan, then delegates to `architect` via `task()`
3. `architect` reads/writes decisions to MCP (`openflo_recall`/`openflo_learn`)
4. `swarm` passes architect's output to `implementer` via task context
5. Each sub-agent uses MCP for persistent memory (decisions, patterns, errors)
6. No direct sub-agent-to-sub-agent communication

Context passing standard:
```
Context: <background, prior decisions, related files>
Goal: <what to produce>
Files: <paths to read or modify>
Constraints: <security, perf, style requirements>
Return: <expected format>
```

## Consequences

- No new infrastructure needed (uses existing `task` tool)
- Swarm agent is the single point of control (clear flow, easy debugging)
- Sub-agents are stateless (no session management)
- Context is explicitly passed (no implicit state surprises)
- MCP provides cross-session persistence (learn once, recall everywhere)

## Alternatives Considered

- **SendMessage-Style**: Would require building messaging infrastructure not available in OpenCode. Rejected as fighting the framework.
- **MCP-Bus-Style**: Agents write tasks to MCP and poll for results. Adds latency and complexity without benefit.
