import { createRequire } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const Database = require("better-sqlite3");

const DATA_DIR = join(__dirname, "..", "..", "..", ".openflo-data");
const DB_PATH = join(DATA_DIR, "memory.db");
const MAX_MEMORIES = 10_000;

let db;

function getDb() {
  if (!db) {
    db = new Database(DB_PATH);
    db.pragma("journal_mode = WAL");
    db.pragma("busy_timeout = 5000");
    db.exec(`
      CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        key TEXT NOT NULL,
        content TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
      CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
    `);
  }
  return db;
}

export function load() {
  try {
    const rows = getDb().prepare("SELECT * FROM memories ORDER BY created_at DESC").all();
    return rows.map(row => ({
      id: row.id,
      key: row.key,
      content: row.content,
      tags: JSON.parse(row.tags || "[]"),
      createdAt: row.created_at,
    }));
  } catch {
    return [];
  }
}

export function createMemory(key, content, tags = []) {
  const d = getDb();
  const count = d.prepare("SELECT COUNT(*) as c FROM memories").get().c;
  if (count >= MAX_MEMORIES) {
    d.prepare("DELETE FROM memories WHERE id IN (SELECT id FROM memories ORDER BY created_at ASC LIMIT ?)")
      .run(count - MAX_MEMORIES + 1);
  }
  const id = require("crypto").randomUUID();
  const tagsStr = JSON.stringify([...new Set((tags || []).map(t => String(t).toLowerCase()))]);
  d.prepare("INSERT INTO memories (id, key, content, tags) VALUES (?, ?, ?, ?)")
    .run(id, key, content, tagsStr);
  const row = d.prepare("SELECT * FROM memories WHERE id = ?").get(id);
  return {
    id: row.id,
    key: row.key,
    content: row.content,
    tags: JSON.parse(row.tags || "[]"),
    createdAt: row.created_at,
  };
}

export function deleteMemory(id) {
  const info = getDb().prepare("DELETE FROM memories WHERE id = ?").run(id);
  return info.changes > 0;
}

export function getMemory(id) {
  const row = getDb().prepare("SELECT * FROM memories WHERE id = ?").get(id);
  if (!row) return null;
  return {
    id: row.id,
    key: row.key,
    content: row.content,
    tags: JSON.parse(row.tags || "[]"),
    createdAt: row.created_at,
  };
}

export function getStats() {
  const d = getDb();
  const total = d.prepare("SELECT COUNT(*) as c FROM memories").get().c;
  const uniqueKeys = d.prepare("SELECT COUNT(DISTINCT key) as c FROM memories").get().c;
  const tagData = d.prepare("SELECT tags FROM memories").all();
  const tagCounts = {};
  for (const row of tagData) {
    for (const t of JSON.parse(row.tags || "[]")) {
      tagCounts[t] = (tagCounts[t] || 0) + 1;
    }
  }
  const { oldest, newest } = d.prepare("SELECT MIN(created_at) as oldest, MAX(created_at) as newest FROM memories").get();
  return {
    total,
    max: MAX_MEMORIES,
    usagePercent: Math.round((total / MAX_MEMORIES) * 100),
    uniqueKeys,
    uniqueTags: Object.keys(tagCounts).length,
    tagCounts,
    entriesByDay: {},
    oldest,
    newest,
  };
}

export function listTags() {
  const tagData = getDb().prepare("SELECT tags FROM memories").all();
  const tagCounts = {};
  for (const row of tagData) {
    for (const t of JSON.parse(row.tags || "[]")) {
      tagCounts[t] = (tagCounts[t] || 0) + 1;
    }
  }
  return Object.entries(tagCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([tag, count]) => ({ tag, count }));
}

export function importFromJson(jsonPath) {
  if (!existsSync(jsonPath)) return 0;
  const d = getDb();
  let imported = 0;
  try {
    const data = JSON.parse(readFileSync(jsonPath, "utf-8"));
    const insert = d.prepare("INSERT OR IGNORE INTO memories (id, key, content, tags, created_at) VALUES (?, ?, ?, ?, ?)");
    const tx = d.transaction((items) => {
      for (const item of items) {
        insert.run(
          item.id || require("crypto").randomUUID(),
          item.key,
          item.content,
          JSON.stringify(item.tags || []),
          item.createdAt || new Date().toISOString()
        );
        imported++;
      }
    });
    tx(data);
  } catch {}
  return imported;
}

export function close() {
  if (db) {
    db.close();
    db = null;
  }
}
