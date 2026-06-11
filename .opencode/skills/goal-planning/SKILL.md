---
name: goal-planning
description: "Decomposes complex goals into actionable sub-tasks with dependency tracking, progress monitoring, and adaptive replanning. Supports parallel task execution, blocker analysis, and automatic replanning when conditions change."
license: MIT
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: planning
  triggers: goal, plan, decompose, task, milestone, roadmap, project, priority
  scope: planning
---

# Goal Planning — Adaptive Task Decomposition

Decomposes complex goals into atomic, dependency-aware sub-tasks. Monitors progress and replans when blocked.

## Goal Decomposition Rules

| Rule | Standard | Why |
|------|----------|-----|
| **Atomic** | Each task = 1-4h of work | Estimable, completable, reviewable |
| **Dependency-aware** | Explicit blocks / blocked-by | Parallel execution |
| **Parallelizable** | Independent tasks run simultaneously | Speed up execution |
| **Verifiable** | Clear "done" condition | No ambiguity |
| **Bounded** | Max 7±2 sub-tasks per level | Manageable scope |
| **Prioritized** | P0 (must), P1 (should), P2 (nice) | Focus on critical path |

## Goal Template

```
Goal: <one sentence describing desired outcome>
Success Criteria: <measurable, verifiable conditions>
Deadline: <YYYY-MM-DD or N/A>
Dependencies: <what must exist first>
Constraints: <budget, tech, time, team>

Sub-tasks:
  - [P0] <Task name> → blocks: [dependent tasks] | depends: [prerequisites]
  - [P1] <Task name> → blocks: [] | depends: []
```

## Progress Tracking

When reporting progress, structure output as:

```
Progress: 3/8 tasks complete (37%)

Blocked:
  - Task 4: waiting on PR review (#42)
  - Task 6: blocked by Task 3 (not started)

Current:
  - Task 3: implementing (80%)
  - Task 5: designing (20%)

Next:
  - Task 4 → can start after Task 3 (PR review)
  - Task 7 → independent, can start now

Risks:
  - Task 6 is on critical path and has no parallel alternative
```

## Adaptive Replanning

When a blocker is detected (blocked > 2h or status not updated):

1. **Analyze blocker**: What's the root cause? Can we work around it?
2. **Adjust plan**:
   - Can a parallel task be started instead?
   - Can the blocked task be split (partial completion)?
   - Can dependencies be reordered?
3. **Update goals**: `openflo_goal_status(save: true)` after replanning

## MCP Tools

| Tool | When | Params | Returns |
|------|------|--------|---------|
| `openflo_goal_save` | Create/update goal plan | `name, plan_json` | Confirmation with ID |
| `openflo_goal_load` | Review plan and progress | `name` | Full plan with status |
| `openflo_goal_status` | Current progress summary | — | All goals, completion %, blockers |
| `openflo_goal_replan` | After blocker detected | `name, blocker_analysis` | Updated plan |
