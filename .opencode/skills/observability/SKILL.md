---
name: observability
description: "Structured logging (JSONL with daily rotation), metrics (counters + latencies), and log querying for MCP tools and agents. Supports component filtering, level-based filtering, and time-range queries. Integrated with OpenFlo HTTP bridge for dashboard display."
license: MIT
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: monitoring
  triggers: log, metric, observe, monitor, trace, debug, inspect, health
  scope: monitoring
---

# Observability — Logging & Metrics

Structured JSONL logging with daily rotation, Prometheus-style metrics (counters + latencies), and queryable log store. Integrated with Web UI dashboard.

## Logging

### Format
```json
{"timestamp":"2026-06-10T20:00:00.000Z","level":"info","component":"tools","message":"Tool called","tool":"openflo_recall","duration":42,"userId":"swarm"}
```

### Levels
| Level | Usage | Color |
|-------|-------|-------|
| `trace` | Debugging, verbose | Gray |
| `debug` | Development details | Blue |
| `info` | Normal operations | Green |
| `warn` | Unexpected but handled | Yellow |
| `error` | Failure, exception | Red |
| `fatal` | Unrecoverable | Red bold |

### Retention
- Hot: 7 days (stdout + file)
- Warm: 30 days (compressed archive)
- Cold: auto-prune after 30d

## Metrics

### Counters
| Metric | Labels | Description |
|--------|--------|-------------|
| `tool_calls_total` | tool, status | Total tool invocations |
| `errors_total` | component, type | Error count |
| `tasks_completed_total` | agent | Completed tasks |

### Latencies
| Metric | Labels | Description |
|--------|--------|-------------|
| `tool_duration_ms` | tool | Tool execution time |
| `task_duration_ms` | agent | Task execution time |

### Gauges
| Metric | Labels | Description |
|--------|--------|-------------|
| `active_connections` | — | Current WebSocket connections |
| `memory_usage_mb` | — | Process memory usage |
| `uptime_seconds` | — | Server uptime |

## MCP Tool

| Tool | Params | Returns |
|------|--------|---------|
| `openflo_logs` | `{ level?, component?, limit?, since? }` | Filtered log entries |

## HTTP Endpoints (via openflo-mcp HTTP bridge)

| Endpoint | Returns |
|----------|---------|
| `GET /v1/health` | `{ status: "ok", uptime, version }` |
| `GET /v1/stats` | Memory, tool counts, latency percentiles |
| `GET /v1/logs?level=error&limit=20` | Filtered log entries |
| `GET /v1/metrics` | Prometheus-format metrics |

## Best Practices

| Do | Don't |
|----|-------|
| Log with structured fields (not string interpolation) | `log.info("User " + id + " logged in")` |
| Include correlation IDs in request chains | Log without context |
| Use appropriate log levels (info for normal, error for failures) | Log everything at error level |
| Set metric labels consistently | Change label schemas without migration |
