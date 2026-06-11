# ADR-001: Agent Format

**Status:** accepted
**Date:** 2026-06-10
**Author:** OpenFlo

## Context

OpenFlo needs a standard format for agent definitions. Each agent must declare its capabilities, permissions, and preferred model tier so the swarm can route tasks correctly.

Options:
1. OpenCode `.md` with YAML frontmatter (native OpenCode format)
2. JSON schema in `opencode.json`
3. Custom registry (JS/TS file exporting agent configs)

## Decision

Use **OpenCode `.md` files with YAML frontmatter** (option 1).

Frontmatter fields:
- `description` — 1-2 sentence purpose
- `mode` — `primary` (user-facing) or `subagent` (swarm-accessible)
- `model` — `anthropic/claude-sonnet-4-6` (smart) or `anthropic/claude-haiku-4-5` (fast)
- `permission` — `{ read: allow|ask, edit: allow|ask|deny, bash: allow|ask|deny }`
- `color` — hex color for swarm UI

Body sections (every agent):
1. **Process** — 3-5 steps (numbered)
2. **Output Format** — structured return data
3. **Error Recovery** — what to do on failure
4. **Anti-Patterns** — what NOT to do

## Consequences

- Agents are self-documenting (readable as plain files)
- OpenCode natively supports this format
- No custom registry infrastructure needed
- Files must be in sync with `opencode.json` agent entries

## Alternatives Considered

- **JSON in opencode.json**: Not self-documenting, hard to version control per-agent
- **Custom registry**: More flexible but requires infrastructure we don't need yet (deferred to Phase 13)
