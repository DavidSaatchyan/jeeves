---
name: swarm
description: "Multi-agent coordination orchestrator for complex multi-step tasks. Assigns work to specialist agents (architect, implementer, reviewer, tester, security, debugger, refactorer) using standardized handoff protocol. Supports parallel execution, consensus, and error recovery patterns. Integrates with memory, goal-planning, and self-learning skills."
license: MIT
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: orchestration
  triggers: complex, multi-step, coordination, delegate, orchestrate, pipeline
  role: orchestrator
  scope: coordination
  output-format: structured result
---

# Swarm — Multi-Agent Orchestration

Coordinates multiple specialist agents for complex tasks. Manages handoffs, parallel execution, quality gates, and error recovery.

## When to Use Swarm

| Trigger | Example | Agents Needed |
|---------|---------|---------------|
| **New feature (full pipeline)** | "Add payment system" | architect → implementer → reviewer → tester → security |
| **Bug fix + test** | "Fix login crash and add test" | debugger → implementer → tester |
| **Code review + security** | "Review PR for quality and security" | reviewer + security (parallel) |
| **Architecture decision** | "Choose DB for new service" | architect → reviewer + security (consensus) |
| **Refactor + test** | "Extract auth service" | architect → implementer → tester |

## Agent Selection Matrix

| Domain | Primary | Follow-up | Suggested Workflow |
|--------|---------|-----------|-------------------|
| System design | architect | implementer → reviewer | Design → Build → Verify |
| Code implementation | implementer | reviewer → tester | Implement → Review → Test |
| Code review | reviewer | implementer (fix) | Review → Fix |
| Testing | tester | reviewer | Test → Review |
| Security audit | security | implementer (fix) → reviewer | Audit → Fix → Verify |
| Debugging | debugger | implementer (fix) → tester | Debug → Fix → Test |
| Refactoring | refactorer | reviewer → tester | Refactor → Review → Test |
| Documentation | documenter | reviewer | Document → Review |
| DevOps/CI/CD | devops | reviewer | Setup → Review |
| Performance | perf | implementer (optimize) | Profile → Fix → Verify |
| Research | researcher | — | Explore → Report |
| Migration | migrator | reviewer → tester | Migrate → Verify → Test |
| Dependencies | deps | tester | Update → Verify |
| Goal planning | plan | architect → implementer | Plan → Design → Build |
| UI/UX design | ux-designer | frontend-developer | Design → Implement |

## Handoff Protocol

Every delegation via `task` tool MUST include:

```
Context: <background, prior decisions, related files, previous agent output>
Goal: <what this agent specifically needs to produce — one clear deliverable>
Files: <paths to read or modify — be specific>
Constraints: <security, performance, style, budget, time>
Return: <expected output format — code, document, analysis>
```

**After handoff:**
1. Read the result
2. Validate against goal
3. If valid → proceed to next step (or store via `openflo_learn`)
4. If invalid → retry with more specific instructions (max 1 retry)
5. If still fails → do it yourself + log failure via `openflo_learn`

## Workflow Patterns

### Design → Build → Verify (4 agents)
```
architect (architecture + ADRs)
  → implementer (implementation)
    → reviewer (code review)
      → tester (tests)
```
For production features where quality matters.

### Parallel Blitz (3 agents, fast)
```
tester + security + reviewer — run simultaneously
```
For quick quality assessment of existing code.

### Consensus (3 agents, risky decisions)
```
architect (proposal)
  → reviewer + security (feedback in parallel)
    → architect (final decision)
```

### Full Pipeline (7 agents, complete feature)
```
architect (design)
  → [implementer (code)]
    → reviewer (review)
      → tester (test)
        → security (audit)
          → documenter (docs)
            → devops (deploy)
```

### Debug Cycle (3 agents)
```
debugger (root cause)
  → tester (failing test)
    → implementer (fix)
      → tester (verify)
```

## Quality Gates

Before marking task complete:
- [ ] Code compiles / lints pass
- [ ] Tests pass (new + existing)
- [ ] No CRITICAL security findings
- [ ] Key decisions stored via `openflo_learn`
- [ ] User informed of what was done and known issues

## Error Recovery

| Situation | Action |
|-----------|--------|
| Agent returns empty | Retry with more specific goal and files |
| Agent returns garbage | Log error, do it yourself |
| Agent times out | Note in log, proceed without that phase |
| Conflicting results | Run third agent to break tie, or ask user |
| Test fails after fix | Return to implementer with failing test output |
| Security finds vuln | Return to implementer with specific fix guidance |

## Resource Management

| Agent Tier | Model | Max Concurrent | Purpose |
|-----------|-------|---------------|---------|
| Smart | deepseek-v4-flash-free | 3 | architect, implementer, security, debugger |
| Fast | big-pickle | 5 | reviewer, tester, researcher, documenter |

## Concurrency Rule

Batch all independent operations into ONE message:
- Read files A, B, C in parallel
- Spawn sub-agents in parallel (when independent)
- Write memory in batch, not one call at a time
- Use `openflo_recall` before starting, `openflo_learn` after completing
