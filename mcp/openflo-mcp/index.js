#!/usr/bin/env node

import { createInterface } from "node:readline";
import { toolDefinitions, handleToolCall } from "./tools.js";
import { createRateLimiter } from "./rate-limiter.js";
import { startHttpServer } from "./http.js";
import { Logger } from "./logger.js";
import { increment, recordLatency } from "./metrics.js";

const rl = createInterface({ input: process.stdin, terminal: false });
let initialized = false;
let reqId = 0;
const rateLimiter = createRateLimiter({ tokensPerSec: 100, maxBurst: 200 });
const log = new Logger("mcp-server");

// Idle timeout: exit after 30 min of inactivity
const IDLE_TIMEOUT_MS = 30 * 60 * 1000;
let idleTimer = null;
function resetIdleTimer() {
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    log.info("Idle timeout reached, exiting");
    process.exit(0);
  }, IDLE_TIMEOUT_MS);
}
resetIdleTimer();

function send(msg) {
  process.stdout.write(JSON.stringify(msg) + "\n");
}

function respond(id, result) {
  send({ jsonrpc: "2.0", id, result });
}

function respondError(id, code, message, data) {
  const err = { code, message };
  if (data) err.data = data;
  send({ jsonrpc: "2.0", id, error: err });
}

function getServerInfo() {
  return {
    name: "openflo-mcp",
    version: "1.0.0",
    description: "Persistent memory server for OpenFlo multi-agent system",
  };
}

rl.on("line", (line) => {
  resetIdleTimer();
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    log("Invalid JSON received, ignoring");
    return;
  }

  const { id, method, params } = msg;

  if (method === "initialize") {
    const clientVersion = params?.protocolVersion || "unknown";
    log.info(`Client initialize (protocol: ${clientVersion})`);

    send({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: "2025-11-25",
        capabilities: {
          tools: {},
        },
        serverInfo: getServerInfo(),
      },
    });

    initialized = true;
    return;
  }

  if (method === "notifications/initialized") {
    initialized = true;
    return;
  }

  if (!initialized && method !== "tools/list") {
    respondError(id, -32000, "Server not initialized. Send initialize first.");
    return;
  }

  if (method === "tools/list") {
    respond(id, { tools: toolDefinitions });
    return;
  }

  if (method === "tools/call") {
    const rlCheck = rateLimiter.check();
    if (!rlCheck.allowed) {
      respondError(id, -32029, "Too many requests. Rate limit exceeded.", {
        retryAfter: rlCheck.retryAfter,
      });
      return;
    }

    resetIdleTimer();
    const toolName = params?.name;
    const args = params?.arguments || {};
    const start = Date.now();
    increment("tool.call");
    (async () => {
    try {
      const result = await handleToolCall(toolName, args);
      const duration = Date.now() - start;
      increment(`tool.${toolName}.success`);
      recordLatency(toolName, duration);
      log.toolCall(toolName, args, duration);
      respond(id, result);
    } catch (err) {
      const duration = Date.now() - start;
      increment("error");
      increment(`tool.${toolName}.error`);
      recordLatency(toolName, duration);
        log.error(`Tool call failed`, { tool: toolName, error: err.message, duration });
      if (err.name === "McpError") {
        respondError(id, err.code, err.message);
      } else {
        respondError(id, -32603, `Internal error: ${err.message}`);
      }
    }
    })();
    return;
  }

  respondError(id, -32601, `Method not found: ${method}`);
});

// Log startup
log.info(`Server started (pid: ${process.pid})`);
log.info(`Waiting for initialize...`);

// Start HTTP server only if OPENFLO_HTTP_PORT is set (off by default)
if (process.env.OPENFLO_HTTP_PORT) {
  startHttpServer(parseInt(process.env.OPENFLO_HTTP_PORT, 10));
  log.info(`HTTP server started on port ${process.env.OPENFLO_HTTP_PORT}`);
}

log.info(`Vector search available via mode: \"semantic\" (loads on first use)`);

// Send capabilities immediately (OpenCode style)
send({
  jsonrpc: "2.0",
  id: null,
  result: {
    capabilities: {
      tools: {},
    },
  },
});
