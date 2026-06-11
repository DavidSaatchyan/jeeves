# ADR-002: MCP Protocol

**Status:** accepted
**Date:** 2026-06-10
**Author:** OpenFlo

## Context

OpenFlo needs a persistent memory system accessible to all agents. The MCP (Model Context Protocol) provides a standard for tool discovery and invocation.

Options:
1. Full MCP 2025-11-25 protocol with complete handshake
2. Minimal JSON-RPC without formal MCP handshake (what we had before)
3. HTTP REST API instead of stdio

## Decision

Use **MCP 2025-11-25 over stdio** (option 1), with gradual extension.

Chosen components:
- Transport: stdio (primary), HTTP (Phase 12 for Web UI)
- Protocol: JSON-RPC 2.0 with initialize → tools/list → tools/call
- Storage: JSON file (Phase 3 → SQLite + HNSW)
- Tools: 5 core tools (recall, learn, forget, list_tags, stats)

Rejected (for now):
- Resources: not needed until Phase 12 (Web UI)
- Prompts: not needed, agents have their own prompts in .md files
- Rate limiting: deferred until T3.1 extension
- Session management: deferred until T3.1 extension

## Consequences

- Compatible with OpenCode v1.17+
- Simple implementation (4 files, ~400 lines)
- No external dependencies
- Easy migration path to SQLite (same tool interface)
- HTTP can be added later without breaking tools

## Alternatives Considered

- **Minimal JSON-RPC** (option 2): Worked but not protocol-compliant, would break if OpenCode enforces handshake
- **HTTP REST** (option 3): Over-engineered for stdio-local use, adds latency
