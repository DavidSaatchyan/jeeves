---
name: memory
description: "Persistent, searchable project memory with SQLite backend. Stores decisions, patterns, gotchas, preferences. Supports keyword, fuzzy (Levenshtein), and semantic (vector embedding) search. Auto-imports from legacy JSON. Max 10,000 entries with tag-based categorization."
license: MIT
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: knowledge
  triggers: remember, recall, store, learn, forget, memory, search, context
  scope: storage
---

# Memory — Project Knowledge Base

Persistent memory system for storing and retrieving project knowledge. SQLite-backed with multi-mode search.

## Storage Rules

| What to Store | When | Tags | Example |
|--------------|------|------|---------|
| Architecture decisions | After decision is made | `decision`, `architecture`, `<domain>` | "Use httpOnly cookies for refresh tokens" |
| Project conventions | When established | `convention`, `style` | "Use kebab-case for files" |
| Gotchas | After debugging | `gotcha`, `bug`, `<domain>` | "Module X crashes on NaN input" |
| Completed tasks | After completion | `task`, `completed`, `<domain>` | "Implemented OAuth2 with Google" |
| User preferences | When expressed | `preference` | "User prefers async/await" |
| Error patterns | When solved | `error`, `fix`, `<domain>` | "Build fails — run npm ci" |
| Code patterns | When discovered | `pattern`, `<language>` | "Service layer pattern example" |

## Search Modes

| Mode | Method | When | Example |
|------|--------|------|---------|
| **Keyword** | Substring matching | Default, fast | `{ query: "refresh token" }` |
| **Tag filter** | Exact tag match | Narrow results | `{ tag: "security" }` |
| **Key match** | Exact key lookup | Retrieve specific | `{ key: "auth-jwt-decision" }` |
| **Fuzzy** | Levenshtein distance | Typo-tolerant | `{ query: "implemantation", fuzzy: true }` |
| **Semantic** | Vector embedding (384-dim) | Conceptual similarity | `{ query: "how to handle auth", mode: "semantic" }` |

## Priority Rules

| Priority | When | Action |
|----------|------|--------|
| **Always recall** | Before designing/implementing anything | `openflo_recall(query="<domain>")` |
| **Always learn** | After completing a task | `openflo_learn(key, content, tags)` |
| **Always tag** | Every memory | Min tag: domain (e.g., `auth`, `frontend`, `db`) |

## Content Rules

| Do | Don't |
|----|-------|
| Store summarized decisions | Store raw tool output |
| Use descriptive keys (e.g., `auth-refresh-decision`) | Use vague keys (`note1`, `memo`) |
| Tag with domain + type | Skip tags entirely |
| Be specific ("15min JWT + rotation") | Be vague ("Use JWT") |
| Include alternatives considered | Store only final decision |

## MCP Tools

| Tool | When | Params | Returns |
|------|------|--------|---------|
| `openflo_recall` | Before starting work | query, tag?, key?, fuzzy?, limit?, mode? | Memory entries with scores |
| `openflo_learn` | After completing a phase | key, content, tags | Confirmation |
| `openflo_forget` | User requests removal | id | Confirmation |
| `openflo_list_tags` | Explore what's stored | — | Tags sorted by frequency |
| `openflo_stats` | Monitor storage | — | Count, usage %, tag distribution |
| `openflo_metrics` | Server health | — | Uptime, call counts, latencies |
| `openflo_pii_scan` | Before reading sensitive files | text, mode | PII findings |

## Storage

- Backend: SQLite (better-sqlite3, WAL mode)
- Location: `.openflo-data/memory.db`
- Legacy: Auto-imports from `.openflo-data/memory.json`
- Max: 10,000 entries (auto-prune oldest)
- Vector: 384-dim float32 via all-MiniLM-L6-v2
