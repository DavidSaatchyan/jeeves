---
name: self-learning
description: "SONA-light learning system that records tool call trajectories, extracts success patterns via MMR (Maximal Marginal Relevance), and maintains a ReasoningBank of problem→solution→outcome chains. Confidence scoring with success=+0.1, failure=-0.15 decay."
license: MIT
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: learning
  triggers: learn, pattern, trajectory, reasoning, improve, feedback
  scope: optimization
---

# Self-Learning — SONA-light System

Records every tool call, extracts successful patterns, and maintains a bank of reasoning chains. Improves over time without manual training.

## How It Works

```
User Action → Tool Call → Trajectory Record → Pattern Extraction → ReasoningBank
                                                  ↕
                                            Feedback Loop (confidence adjust)
```

### 1. Trajectory Recording (automatic via plugin)
Every tool call is recorded with:
- Tool name and parameters
- Success/failure status
- Session chain (logged together)
- Timestamp and agent

### 2. Pattern Extraction (on demand)
`openflo_patterns { tool, context }`:
- Searches successful trajectories
- Ranks by MMR (diversity + relevance)
- Returns top 3 patterns

### 3. ReasoningBank (manual + automatic)
`openflo_reasoning { query }`:
- Stores: problem → attempted solution → outcome
- Each entry has: confidence (0.0-1.0), tags, usage count
- Confidence: success += 0.1, failure -= 0.15 (min 0, max 1)

### 4. Feedback Loop (plugin)
After each completed task:
- Success → increase confidence of used patterns
- Failure → decrease confidence, log RCA
- User feedback → adjust accordingly

## When to Use

| Tool | When | Example |
|------|------|---------|
| `openflo_patterns` | Before starting familiar task | `{ tool: "edit", context: "refactor auth middleware" }` |
| `openflo_reasoning` | When stuck on a problem | `{ query: "database connection pool exhaustion" }` |
| `openflo_recall(mode:semantic)` | Fuzzy recall of past decisions | `{ query: "why did we choose PostgreSQL", mode: "semantic" }` |

## Best Practices

| Do | Don't |
|----|-------|
| After solving tricky problem, check ReasoningBank first | Store every trivial action |
| Before refactoring, check patterns for similar code | Rely only on raw tool history |
| Use semantic mode for conceptual queries | Store personally identifiable info |
| Let patterns auto-discover from trajectories | Manually curate patterns |

## MCP Tools

| Tool | Params | Returns |
|------|--------|---------|
| `openflo_patterns` | `{ tool, context }` | Top 3 matching patterns with relevance score |
| `openflo_reasoning` | `{ query, limit, minConfidence }` | Matching problem→solution→outcome entries |

## Data

- Storage: SQLite (same as memory, `trajectories` + `patterns` + `reasoning` tables)
- Trajectory retention: 30 days (auto-prune)
- Pattern limit: 500 (auto-prune lowest confidence + oldest)
- Confidence floor: 0.1 (old/unused patterns decay to 0.1, not 0)
