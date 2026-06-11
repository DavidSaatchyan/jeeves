import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { loadIdentity, signMessage, verifySignature, storePeer, getPeers } from "./identity.js";
import { calculateTrust } from "./trust.js";
import { scanPII } from "../openflo-mcp/pii.js";
import { createMemory } from "../openflo-mcp/store.js";
import { Logger } from "../openflo-mcp/logger.js";

const log = new Logger("federation");

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const TASK_TIMEOUT = 5 * 60 * 1000;
const taskQueue = new Map();

const identity = loadIdentity();

export function getPeerId() {
  return identity.peerId;
}

export function queueTask(task) {
  const id = task.task_id || require("crypto").randomUUID();
  taskQueue.set(id, {
    ...task,
    status: "pending",
    createdAt: new Date().toISOString(),
  });
  return id;
}

export function getTask(id) {
  return taskQueue.get(id) || null;
}

export function updateTaskStatus(id, status, result) {
  const task = taskQueue.get(id);
  if (!task) return null;
  task.status = status;
  if (result !== undefined) task.result = result;
  task.updatedAt = new Date().toISOString();
  return task;
}

export function buildSignedMessage(type, payload, targetPeerId) {
  const msg = {
    type,
    task_id: require("crypto").randomUUID(),
    sender: identity.peerId,
    target: targetPeerId,
    payload,
    timestamp: new Date().toISOString(),
  };

  msg.signature = signMessage(identity.privateKey, { type: msg.type, task_id: msg.task_id, payload: msg.payload });
  return msg;
}

export function verifyMessage(msg) {
  const peers = getPeers();
  const peer = peers[msg.sender];
  if (!peer) return { valid: false, reason: "unknown-peer" };

  const trust = calculateTrust(peer);
  if (!trust.trusted) {
    return { valid: false, reason: "trust-below-threshold", trust: trust.score };
  }

  const valid = verifySignature(peer.publicKey, { type: msg.type, task_id: msg.task_id, payload: msg.payload }, msg.signature);
  return { valid, peer: msg.sender, trust: trust.score };
}

export function handleIncomingMessage(msg) {
  const verification = verifyMessage(msg);
  if (!verification.valid) {
    return { handled: false, error: `Invalid message: ${verification.reason}` };
  }

  storePeer(msg.sender, null, { lastSeen: new Date().toISOString() });

  switch (msg.type) {
    case "task_request": {
      const taskId = queueTask(msg.payload);
      createMemory(
        `federation:task:${taskId}`,
        `Received task from ${msg.sender}: ${msg.payload.goal || "no goal"}`,
        ["federation", "task", "received", msg.sender]
      );
      log.info("Task received", { taskId, sender: msg.sender });
      return { handled: true, taskId, action: "queued" };
    }

    case "task_response": {
      const existing = getTask(msg.payload.task_id);
      if (existing) {
        updateTaskStatus(msg.payload.task_id, msg.payload.status, msg.payload.result);
        createMemory(
          `federation:response:${msg.payload.task_id}`,
          `Task ${msg.payload.task_id} completed by ${msg.sender}: ${msg.payload.status}`,
          ["federation", "task", "response", msg.sender]
        );
      }
      return { handled: true, status: msg.payload.status };
    }

    case "sync_memory": {
      if (msg.payload?.memories) {
        const count = msg.payload.memories.length;
        for (const mem of msg.payload.memories.slice(0, 50)) {
          createMemory(
            `federation:sync:${msg.sender}:${mem.key}`,
            mem.content || "",
            [...(mem.tags || []), "federation", "synced", msg.sender]
          );
        }
        return { handled: true, synced: count };
      }
      return { handled: true, synced: 0 };
    }

    case "heartbeat":
      return { handled: true, status: "alive" };

    default:
      return { handled: false, error: `unknown-type: ${msg.type}` };
  }
}

export function getToolDefinitions() {
  return [
    {
      name: "openflo_federation_peers",
      description: "List known federation peers with trust scores",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "openflo_federation_send",
      description: "Prepare a signed message for a peer (PII-scanned before sending)",
      inputSchema: {
        type: "object",
        properties: {
          target: { type: "string", description: "Target peer ID" },
          type: { type: "string", enum: ["task_request", "task_response", "sync_memory", "heartbeat"] },
          payload: { type: "object", description: "Message payload" },
        },
        required: ["target", "type", "payload"],
      },
    },
    {
      name: "openflo_federation_status",
      description: "Get federation identity and queue status",
      inputSchema: { type: "object", properties: {} },
    },
  ];
}

export function handleFederationTool(name, args) {
  switch (name) {
    case "openflo_federation_peers": {
      const peers = getPeers();
      const entries = Object.entries(peers);
      if (entries.length === 0) {
        return { content: [{ type: "text", text: "No federation peers known." }] };
      }
      const lines = ["Known Peers:"];
      for (const [id, p] of entries) {
        const trust = calculateTrust(p);
        lines.push(`  ${id}: score=${trust.score} trusted=${trust.trusted} success=${p.successCount} fail=${p.failCount}`);
      }
      return { content: [{ type: "text", text: lines.join("\n") }] };
    }

    case "openflo_federation_send": {
      if (!args?.target || !args?.type || !args?.payload) throw mcpError(-32602, "target, type, payload required");

      // T10.3: PII scan before sending
      const payloadText = JSON.stringify(args.payload);
      const piiResult = scanPII(payloadText, { mode: "block" });
      if (piiResult.blocked) {
        throw mcpError(-32099, `Federation send blocked: PII detected in payload (${piiResult.highConfidence} high-confidence findings)`);
      }

      const msg = buildSignedMessage(args.type, args.payload, args.target);
      const memKey = `federation:outgoing:${msg.task_id}`;
      createMemory(
        memKey,
        `Sent ${args.type} to ${args.target}: ${JSON.stringify(args.payload).slice(0, 200)}`,
        ["federation", "outgoing", args.type, args.target]
      );
      log.info("Message prepared", { target: args.target, type: args.type, taskId: msg.task_id });
      return {
        content: [{
          type: "text",
          text: `Message prepared for ${args.target}:\n  Type: ${args.type}\n  Task ID: ${msg.task_id}\n  PII scan: ✓\n  Signed: ✓\n  (requires WebSocket transport to send)`,
        }],
      };
    }

    case "openflo_federation_status": {
      const peers = getPeers();
      const activeTasks = [...taskQueue.values()].filter(t => t.status === "pending" || t.status === "running");
      return {
        content: [{
          type: "text",
          text: [
            `Federation Status:`,
            `  Peer ID: ${identity.peerId}`,
            `  Known peers: ${Object.keys(peers).length}`,
            `  Queued tasks: ${taskQueue.size}`,
            `  Active: ${activeTasks.length}`,
          ].join("\n"),
        }],
      };
    }

    default:
      throw mcpError(-32601, `Tool not found: ${name}`);
  }
}

function mcpError(code, message) {
  const err = new Error(message);
  err.code = code;
  err.name = "McpError";
  return err;
}
