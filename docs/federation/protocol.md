# OpenFlo Federation Protocol v1

## Overview

Federation allows multiple OpenFlo instances to communicate, share tasks, and sync memory.
Peers discover each other via WebSocket, authenticate with ed25519 keys, and exchange signed messages.

## Transport

- **Primary:** WebSocket Secure (wss://)
- **Fallback:** TCP JSON-RPC (localhost dev only)
- **Port:** 54321 (default)
- **Heartbeat:** ping/pong every 30s, timeout 10s
- **Reconnect:** exponential backoff (1s, 2s, 4s, 8s, max 60s)

## Message Format

```json
{
  "type": "task_request" | "task_response" | "sync_memory" | "heartbeat" | "error",
  "task_id": "uuid",
  "sender": "peer-id (ed25519 public key hash)",
  "payload": { ... },
  "signature": "base64-encoded ed25519 signature",
  "timestamp": "ISO-8601"
}
```

## Handshake

1. Peer A connects to Peer B
2. Peer A sends `identity` message with its public key
3. Peer B verifies, responds with its identity
4. Both store peer info
5. Optional: request trust score

## Task Relay

- `task_request`: send a task to a peer (with context, goal, files)
- `task_response`: return result (completed/failed with output)
- Timeout: 5 min → fail
- Queue: pending → running → completed/failed

## Identity

- ed25519 keys stored in `.openflo-data/federation/keys/`
- Peer ID = SHA256(public key).hex[:16]
- Messages are signed with private key
- Signatures verified with stored public key

## Security

- All messages signed
- PII pipeline filters before sending (T6.3)
- Trust scoring: 0.4×success_rate + 0.2×uptime + 0.2×threat_ratio + 0.2×age
- Peers below trust threshold (0.3) are rejected
