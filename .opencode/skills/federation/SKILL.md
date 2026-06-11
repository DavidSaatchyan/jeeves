---
name: federation
description: "Multi-instance federation for distributed OpenFlo agents. ed25519 identity per instance, signed messages, trust scoring (success×0.4 + uptime×0.2 + threat×0.2 + age×0.2), WebSocket transport with exponential backoff reconnect. Supports task delegation across instances."
license: MIT
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: network
  triggers: federation, peer, remote, distribute, sync, share, coordinate, multi-instance
  scope: coordination
---

# Federation — Cross-Instance Coordination

Connects multiple OpenFlo instances for distributed agent coordination. Identity-based trust, signed messaging, resilient transport.

## Architecture

```
Instance A (home)              Instance B (remote)
  │                                │
  ├─ identity (ed25519)           ├─ identity (ed25519)
  ├─ trust store                  ├─ trust store
  ├─ task queue                   ├─ task queue
  └─ WebSocket ←──── TLS ─────→ └─ WebSocket
        transport                      transport
```

## Identity

- Ed25519 key pair per instance (generated on init)
- Public key = peer ID (hex-encoded)
- All messages signed with private key
- Key rotation supported (new key = new identity)

## Trust Scoring

| Factor | Weight | Calculation |
|--------|--------|-------------|
| Task success rate | 0.4 | successful_tasks / total_tasks |
| Uptime | 0.2 | uptime_hours / 720 (30d) |
| Threat assessment | 0.2 | 1.0 - reported_threats / max_threats |
| Peer age | 0.2 | min(age_days / 30, 1.0) |

- **Threshold**: 0.3 (below = tasks rejected)
- **Decay**: -0.05 per week without interaction
- **Block**: manual block overrides all scores

## Task Delegation

```
Home Instance                    Remote Instance
  │                                   │
  ├─ sign task message                │
  ├─ check trust > 0.3               │
  ├─ PII scan task data               │
  ├─ send ───── signed task ──────→   │
  │                                   ├─ verify signature
  │                                   ├─ check home's trust
  │                                   ├─ execute task
  │                                   ├─ sign result
  │                             ←─────┼─ return result
  ├─ verify result signature          │
  ├─ update trust score               │
```

## Transport

- WebSocket (TLS in production, plain for dev)
- Exponential backoff reconnect: 5s → 15s → 60s → 300s (cap)
- Outbox: persistent queue for undelivered messages
- Heartbeat: ping/pong every 30s, timeout 10s

## Security

- All messages signed (ed25519)
- PII scan before send (auto-redact)
- No message relay (peer-to-peer only)
- Rate limit: 10 tasks/min per peer
- Threat reporting: peers can report malicious behavior

## MCP Tools

| Tool | When | Params |
|------|------|--------|
| `openflo_federation_peers` | List connected peers | — |
| `openflo_federation_send` | Delegate task to peer | peerId, task, payload |
| `openflo_federation_trust` | Check/view peer trust | peerId? (all if empty) |
