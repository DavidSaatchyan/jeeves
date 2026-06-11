---
name: consensus
description: "Multi-agent consensus protocol for architectural decisions. Supports three consensus patterns: Raft (single proposer, follower approval), Byzantine (tolerates dissent with weighted voting), and Gossip (emergent agreement). Uses reputation-weighted voting for conflict resolution."
license: MIT
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: decision
  triggers: consensus, vote, decide, agree, resolve conflict, decision, arbitration
  scope: decision-making
---

# Consensus — Multi-Agent Decision Protocol

Reaches agreement among multiple agents on architectural decisions, technical choices, and conflict resolution.

## Consensus Patterns

| Pattern | When | How | Speed |
|---------|------|-----|-------|
| **Raft** | Single decision, clear options | One proposer → followers vote → majority wins | Fast (2 rounds) |
| **Byzantine** | High-risk, disagreement expected | All agents propose → weighted vote by reputation | Medium (3 rounds) |
| **Gossip** | Emergent, exploratory | Agents exchange pairwise → converge over time | Slow (N rounds) |

## When to Use Consensus

| Situation | Pattern | Example |
|-----------|---------|---------|
| Architecture decision | Raft | "Choose DB: PostgreSQL vs CockroachDB" |
| Conflict resolution | Byzantine | "Two agents disagree on approach" |
| Exploratory design | Gossip | "What should the data model look like?" |
| Security audit results | Byzantine | "Is this vulnerability acceptable risk?" |
| Technology selection | Raft | "Select frontend framework" |

## Voting Rules

| Rule | Standard | Reason |
|------|----------|--------|
| **Quorum** | > 50% of eligible agents must vote | Prevent minority decisions |
| **Majority** | > 50% of votes cast | Simple, clear |
| **Super-majority** | > 66% for high-risk decisions | Higher confidence |
| **Veto** | Security architect can veto security decisions | Security authority |
| **Abstain** | Allow abstention if out of expertise | Don't vote ignorantly |
| **Timebox** | Max 3 rounds of voting | Avoid infinite loop |

## MCP Tools

| Tool | When | Params | Returns |
|------|------|--------|---------|
| `openflo_consensus_vote` | Start a vote | `proposal, options, pattern, agents` | Vote ID, status |
| `openflo_consensus_tally` | Get results | `voteId` | Outcome, breakdown, dissent |
