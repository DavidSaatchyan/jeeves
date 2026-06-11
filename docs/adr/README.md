# ADR Process

## When to write an ADR
- Any architectural decision that affects multiple components
- Choice between alternatives (why A over B)
- Public API decisions
- Protocol/format decisions
- Dependency choices that are hard to reverse

## Template

```markdown
# ADR-NNN: Title

**Status:** [proposed | accepted | deprecated | superseded]
**Date:** YYYY-MM-DD
**Author:** OpenFlo

## Context
What is the problem? What are the constraints?

## Decision
What was chosen and why.

## Consequences
What trade-offs were accepted? What becomes easier/harder?

## Alternatives Considered
- Option A: pros/cons
- Option B: pros/cons
```

## Rules
- One ADR per decision
- Number sequentially (ADR-001, ADR-002…)
- Never delete ADRs — mark as `superseded` with a link to the new ADR
- Keep under 200 lines
