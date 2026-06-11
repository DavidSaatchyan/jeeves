---
name: web-ui
description: "Browser-based dashboard for OpenFlo observability. Displays system stats (uptime, memory, tool call counts), memories with search + delete, goal progress with status tracking, connected federation peers with trust scores, and log viewer with level/component filtering. Dark theme, auto-refresh polling, responsive layout."
license: MIT
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: frontend
  triggers: dashboard, web UI, visualize, observe, monitor, admin panel
  scope: display
---

# Web UI — Observability Dashboard

Browser-based dashboard for monitoring OpenFlo system health, memories, goals, peers, and logs.

## Dashboard Tabs

| Tab | Content | Refresh | Data Source |
|-----|---------|---------|-------------|
| **Stats** | Uptime, memory, tool call counts, latency | 5s | `GET /v1/stats` + `/v1/health` |
| **Memories** | Recent entries with search, tag filter, delete | 10s | `POST /v1/memories` (via MCP) |
| **Goals** | Goal progress, task status, blockers | 10s | `openflo_goal_status` |
| **Peers** | Connected federation peers, trust scores | 15s | `openflo_federation_peers` |
| **Logs** | Filtered log viewer by level, component | 15s | `GET /v1/logs` |

## File Structure

| File | Purpose |
|------|---------|
| `index.html` | Dashboard layout, 5 tabs, dark theme (50 lines) |
| `app.js` | Polling logic, API calls, DOM updates (65 lines) |
| `style.css` | Dark theme CSS grid, cards, responsive (120 lines) |

## How It Works

1. HTTP server (`mcp/openflo-mcp/http.js`) exposes REST endpoints
2. Dashboard polls endpoints at configured intervals
3. Auto-updates DOM with new data
4. Dark theme with card-based layout

## Prerequisites

- MCP server running with HTTP bridge enabled
- Open `web/index.html` in browser
- Default port: 3001 (configurable)

## Data Flow

```
Browser (web/index.html) ← HTTP GET → openflo-mcp HTTP bridge (port 3001)
                                           │
                                     MCP tools (stats, logs, goals)
                                           │
                                     SQLite / in-memory store
```

## Customization

| Parameter | Location | Default |
|-----------|----------|---------|
| HTTP port | `mcp/openflo-mcp/tools.js` | 3001 |
| Poll interval | `web/app.js` | stats: 5s, memories: 10s, logs: 15s |
| Theme colors | `web/style.css` CSS variables | Dark (#0f172a base) |
