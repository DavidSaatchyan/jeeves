import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { getPeers, storePeer, loadIdentity } from "./identity.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const TRANSPORT_DIR = join(__dirname, "..", "..", ".openflo-data", "federation", "transport");
const OUTBOX_FILE = join(TRANSPORT_DIR, "outbox.json");

if (!existsSync(TRANSPORT_DIR)) mkdirSync(TRANSPORT_DIR, { recursive: true });

let wsClients = new Map(); // peerId -> WebSocket
let serverInstance = null;
let reconnectTimers = new Map();

const identity = loadIdentity();

// ---- Outbox (offline queue) ----

function loadOutbox() {
  try { return JSON.parse(readFileSync(OUTBOX_FILE, "utf-8")); }
  catch { return []; }
}

function saveOutbox(outbox) {
  writeFileSync(OUTBOX_FILE, JSON.stringify(outbox, null, 2));
}

// ---- WebSocket Server ----

export function startServer(port = 4322) {
  try {
    const WebSocket = require("ws");
    serverInstance = new WebSocket.Server({ port });

    serverInstance.on("connection", (ws, req) => {
      const peerId = req.url?.slice(1) || "unknown";
      ws.peerId = peerId;
      wsClients.set(peerId, ws);
      storePeer(peerId, null, { lastSeen: new Date().toISOString(), transport: "ws" });

      ws.on("message", (data) => {
        try {
          const msg = JSON.parse(data.toString());
          const { handleIncomingMessage } = require("./task.js");
          const result = handleIncomingMessage(msg);
          ws.send(JSON.stringify({ type: "response", task_id: msg.task_id, result }));
        } catch {}
      });

      ws.on("close", () => {
        wsClients.delete(peerId);
      });
    });

    return { port, status: "running" };
  } catch (e) {
    return { port, status: "failed", error: e.message };
  }
}

export function stopServer() {
  if (serverInstance) serverInstance.close();
  serverInstance = null;
}

// ---- WebSocket Client ----

export function connectToPeer(peerId, url) {
  if (wsClients.has(peerId)) return { status: "already-connected" };

  try {
    const WebSocket = require("ws");
    const ws = new WebSocket(url + "/" + identity.peerId);

    ws.on("open", () => {
      wsClients.set(peerId, ws);
      storePeer(peerId, null, { lastSeen: new Date().toISOString(), transport: "ws" });

      // Flush outbox
      const outbox = loadOutbox();
      const unsent = outbox.filter(m => m.target === peerId);
      for (const msg of unsent) {
        ws.send(JSON.stringify(msg));
      }
      saveOutbox(outbox.filter(m => m.target !== peerId));
    });

    ws.on("message", (data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (msg.type === "heartbeat") return;
        const { handleIncomingMessage } = require("./task.js");
        handleIncomingMessage(msg);
      } catch {}
    });

    ws.on("close", () => {
      wsClients.delete(peerId);
      // Reconnect with exponential backoff: 5s, 15s, 60s
      scheduleReconnect(peerId, url);
    });

    ws.on("error", () => {
      wsClients.delete(peerId);
      scheduleReconnect(peerId, url);
    });

    return { status: "connecting" };
  } catch (e) {
    scheduleReconnect(peerId, url);
    return { status: "failed", error: e.message };
  }
}

function scheduleReconnect(peerId, url) {
  if (reconnectTimers.has(peerId)) return;

  const delays = [5000, 15000, 60000];
  let attempt = 0;

  function tryReconnect() {
    if (attempt >= delays.length) {
      reconnectTimers.delete(peerId);
      return;
    }
    reconnectTimers.set(peerId, setTimeout(() => {
      attempt++;
      if (!wsClients.has(peerId)) {
        connectToPeer(peerId, url);
      }
      if (!wsClients.has(peerId) && attempt < delays.length) {
        tryReconnect();
      } else {
        reconnectTimers.delete(peerId);
      }
    }, delays[attempt] || 60000));
  }

  tryReconnect();
}

// ---- Send Message ----

export function sendMessage(peerId, msg) {
  const ws = wsClients.get(peerId);
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify(msg));
    return { sent: true, transport: "ws" };
  }

  // Offline: queue to outbox
  const outbox = loadOutbox();
  outbox.push({ target: peerId, ...msg, queuedAt: new Date().toISOString() });
  saveOutbox(outbox);
  return { sent: false, transport: "outbox", queued: true };
}

// ---- Status ----

export function getTransportStatus() {
  return {
    peerId: identity.peerId,
    connected: Array.from(wsClients.entries()).map(([id, ws]) => ({
      peerId: id,
      readyState: ws.readyState,
    })),
    outboxSize: loadOutbox().length,
    serverRunning: serverInstance !== null,
    pendingReconnects: reconnectTimers.size,
  };
}
