import { embed, cosineSimilarityBatch } from "../embeddings.js";
import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const DATA_DIR = join(__dirname, "..", "..", "..", ".openflo-data");
const DB_PATH = join(DATA_DIR, "memory.db");

let db = null;
let vectorMode = false;

function getDb() {
  if (db) return db;
  try {
    const Database = require("better-sqlite3");
    db = new Database(DB_PATH);
    db.pragma("journal_mode = WAL");
    // Add embedding column if not exists
    try { db.exec("ALTER TABLE memories ADD COLUMN embedding TEXT"); } catch {}
    return db;
  } catch {
    return null;
  }
}

export function isVectorMode() {
  return vectorMode;
}

export async function initVectorSearch() {
  const d = getDb();
  if (!d) return false;

  // Check if we have any embeddings
  const count = d.prepare("SELECT COUNT(*) as c FROM memories WHERE embedding IS NOT NULL").get().c;
  const total = d.prepare("SELECT COUNT(*) as c FROM memories").get().c;
  if (total > 0 && count === 0) {
    process.stderr.write(`[openflo-mcp] Generating embeddings for ${total} memories...\n`);
    const rows = d.prepare("SELECT id, content FROM memories WHERE embedding IS NULL").all();
    for (let i = 0; i < rows.length; i++) {
      const vec = await embed(rows[i].content);
      if (vec) {
        d.prepare("UPDATE memories SET embedding = ? WHERE id = ?").run(JSON.stringify(vec), rows[i].id);
      }
      if ((i + 1) % 50 === 0) {
        process.stderr.write(`[openflo-mcp]  Embedded ${i + 1}/${rows.length}\n`);
      }
    }
  }
  vectorMode = true;
  return true;
}

export async function semanticSearch(query, options = {}) {
  const d = getDb();
  if (!d) return [];

  const limit = Math.min(Math.max(1, options.limit || 10), 50);
  const queryVec = await embed(query);
  if (!queryVec) return [];

  let sql = "SELECT id, key, content, tags, created_at, embedding FROM memories WHERE embedding IS NOT NULL";
  const params = [];

  if (options.tag) {
    sql += " AND tags LIKE ?";
    params.push(`%"${options.tag.toLowerCase()}"%`);
  }

  if (options.key) {
    sql += " AND key = ?";
    params.push(options.key);
  }

  const rows = d.prepare(sql).all(...params);
  if (rows.length === 0) return [];

  const vectors = rows.map(r => JSON.parse(r.embedding));
  const scored = cosineSimilarityBatch(queryVec, vectors);

  return scored.slice(0, limit).map(s => {
    const row = rows[s.index];
    return {
      id: row.id,
      key: row.key,
      content: row.content,
      tags: JSON.parse(row.tags || "[]"),
      createdAt: row.created_at,
      score: Math.round(s.score * 1000) / 1000,
    };
  });
}

export async function addEmbedding(id, content) {
  const d = getDb();
  if (!d) return;
  try {
    const vec = await embed(content);
    if (vec) {
      d.prepare("UPDATE memories SET embedding = ? WHERE id = ?").run(JSON.stringify(vec), id);
    }
  } catch {
    // Silently skip — model may not be loaded
  }
}
