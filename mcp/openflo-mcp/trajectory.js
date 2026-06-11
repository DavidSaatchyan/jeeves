import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createMemory } from "./store.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const DATA_DIR = join(__dirname, "..", "..", ".openflo-data");

let db = null;

function getDb() {
  if (db) return db;
  try {
    const Database = require("better-sqlite3");
    db = new Database(join(DATA_DIR, "memory.db"));
    db.pragma("journal_mode = WAL");
    db.exec(`
      CREATE TABLE IF NOT EXISTS trajectories (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        parent_id TEXT,
        tool_name TEXT NOT NULL,
        args TEXT,
        result TEXT,
        success INTEGER NOT NULL DEFAULT 1,
        duration_ms INTEGER,
        reasoning TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_traj_session ON trajectories(session_id);
      CREATE INDEX IF NOT EXISTS idx_traj_tool ON trajectories(tool_name);
    `);
    return db;
  } catch { return null; }
}

export function recordToolCall({ sessionId, toolName, args, result, success, durationMs, reasoning, parentId }) {
  const d = getDb();
  if (!d) return;

  const id = require("crypto").randomUUID();
  d.prepare(`
    INSERT INTO trajectories (id, session_id, parent_id, tool_name, args, result, success, duration_ms, reasoning)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    id,
    sessionId || "default",
    parentId || null,
    toolName,
    args ? JSON.stringify(args).slice(0, 5000) : null,
    result ? JSON.stringify(result).slice(0, 5000) : null,
    success ? 1 : 0,
    durationMs || 0,
    reasoning || null
  );

  // Auto-learn: if successful, store as positive pattern
  if (success && reasoning) {
    createMemory(
      `trajectory:${toolName}:${Date.now()}`,
      `Successful ${toolName}: ${reasoning}`,
      ["trajectory", "success", toolName]
    );
  }
}

export function getTrajectories(options = {}) {
  const d = getDb();
  if (!d) return [];

  const { sessionId, toolName, limit = 50, success } = options;
  let sql = "SELECT * FROM trajectories WHERE 1=1";
  const params = [];

  if (sessionId) { sql += " AND session_id = ?"; params.push(sessionId); }
  if (toolName) { sql += " AND tool_name = ?"; params.push(toolName); }
  if (success !== undefined) { sql += " AND success = ?"; params.push(success ? 1 : 0); }

  sql += " ORDER BY created_at DESC LIMIT ?";
  params.push(Math.min(limit, 200));

  return d.prepare(sql).all(...params);
}

export function getSessionChain(sessionId) {
  const d = getDb();
  if (!d) return [];
  return d.prepare(`
    WITH RECURSIVE chain AS (
      SELECT * FROM trajectories WHERE id = (
        SELECT id FROM trajectories WHERE session_id = ? ORDER BY created_at DESC LIMIT 1
      )
      UNION ALL
      SELECT t.* FROM trajectories t
      JOIN chain c ON t.id = c.parent_id
    )
    SELECT * FROM chain ORDER BY created_at
  `).all(sessionId);
}
