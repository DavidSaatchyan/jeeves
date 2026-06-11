import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

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
      CREATE TABLE IF NOT EXISTS reasoning_bank (
        id TEXT PRIMARY KEY,
        problem TEXT NOT NULL,
        solution TEXT NOT NULL,
        outcome TEXT,
        tags TEXT DEFAULT '[]',
        confidence REAL NOT NULL DEFAULT 0.5,
        source TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_reasoning_tags ON reasoning_bank(tags);
    `);
    return db;
  } catch { return null; }
}

export function addReasoning(problem, solution, { outcome, tags, source, confidence } = {}) {
  const d = getDb();
  if (!d) return null;

  const id = require("crypto").randomUUID();
  d.prepare(`
    INSERT INTO reasoning_bank (id, problem, solution, outcome, tags, confidence, source)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(id, problem, solution, outcome || null, JSON.stringify(tags || []), confidence || 0.5, source || null);

  return { id, problem, solution };
}

export function findReasoning(query, options = {}) {
  const d = getDb();
  if (!d) return [];

  const { limit = 5, minConfidence = 0 } = options;
  const q = query.toLowerCase();

  const rows = d.prepare("SELECT * FROM reasoning_bank WHERE confidence >= ? ORDER BY confidence DESC").all(minConfidence);

  const scored = rows.map(r => {
    let score = 0;
    const problem = r.problem.toLowerCase();
    const solution = r.solution.toLowerCase();
    const tags = JSON.parse(r.tags || "[]").join(" ").toLowerCase();

    if (problem.includes(q)) score += 3;
    if (solution.includes(q)) score += 2;
    if (tags.includes(q)) score += 1;

    for (const term of q.split(/\s+/).filter(Boolean)) {
      if (problem.includes(term)) score += 1.5;
      if (solution.includes(term)) score += 1;
    }

    return { ...r, score: score + r.confidence, tags: JSON.parse(r.tags || "[]") };
  });

  return scored.filter(r => r.score > 0).sort((a, b) => b.score - a.score).slice(0, limit);
}

export function updateOutcome(id, outcome, success) {
  const d = getDb();
  if (!d) return;

  const existing = d.prepare("SELECT * FROM reasoning_bank WHERE id = ?").get(id);
  if (!existing) return;

  const newConfidence = Math.max(0.1, Math.min(1.0,
    existing.confidence + (success ? 0.1 : -0.15)
  ));

  d.prepare("UPDATE reasoning_bank SET outcome = ?, confidence = ?, updated_at = datetime('now') WHERE id = ?")
    .run(outcome, newConfidence, id);
}

export function getToolDefinition() {
  return {
    name: "openflo_reasoning",
    description: "Query the ReasoningBank for past problems and solutions",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Problem description to search for" },
        limit: { type: "number", description: "Max results", default: 5 },
        minConfidence: { type: "number", description: "Minimum confidence (0-1)", default: 0 },
      },
      required: ["query"],
    },
  };
}

export function handleReasoningQuery(args) {
  const query = String(args.query || "").trim();
  if (!query) throw new (class extends Error {
    constructor() { super("query is required"); this.code = -32602; this.name = "McpError"; }
  })();

  const results = findReasoning(query, {
    limit: Math.min(args.limit || 5, 20),
    minConfidence: args.minConfidence || 0,
  });

  if (results.length === 0) {
    return { content: [{ type: "text", text: `No reasoning found for "${query}".` }] };
  }

  const text = results.map((r, i) =>
    `[${i + 1}] Problem: ${r.problem}\n    Solution: ${r.solution}\n    Confidence: ${Math.round(r.confidence * 100)}%\n    Tags: ${r.tags.join(", ")}${r.outcome ? `\n    Outcome: ${r.outcome}` : ""}`
  ).join("\n\n");

  return { content: [{ type: "text", text }] };
}
