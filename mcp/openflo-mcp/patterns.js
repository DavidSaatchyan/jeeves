import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { load } from "./store.js";

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
      CREATE TABLE IF NOT EXISTS patterns (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        trigger_tools TEXT NOT NULL DEFAULT '[]',
        success_rate REAL NOT NULL DEFAULT 0.5,
        weight REAL NOT NULL DEFAULT 1.0,
        tags TEXT DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_used TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_patterns_name ON patterns(name);
    `);
    return db;
  } catch { return null; }
}

export function registerPattern(name, description, triggerTools = [], tags = []) {
  const d = getDb();
  if (!d) return null;

  const existing = d.prepare("SELECT * FROM patterns WHERE name = ?").get(name);
  if (existing) return existing;

  const id = require("crypto").randomUUID();
  d.prepare(`
    INSERT INTO patterns (id, name, description, trigger_tools, tags)
    VALUES (?, ?, ?, ?, ?)
  `).run(id, name, description, JSON.stringify(triggerTools), JSON.stringify(tags));

  return { id, name, description, triggerTools, tags };
}

export function findMatchingPatterns(toolName, context = "") {
  const d = getDb();
  if (!d) return [];

  const patterns = d.prepare("SELECT * FROM patterns ORDER BY weight DESC, success_rate DESC").all();
  const matches = [];

  for (const p of patterns) {
    const triggers = JSON.parse(p.trigger_tools || "[]");
    const tags = JSON.parse(p.tags || "[]");

    // Tool name match
    if (triggers.length > 0 && !triggers.includes(toolName)) continue;

    // Context relevance
    let relevance = 0;
    const contextLower = context.toLowerCase();
    const descLower = p.description.toLowerCase();
    const nameLower = p.name.toLowerCase();

    if (contextLower.includes(nameLower) || contextLower.includes(descLower.slice(0, 30))) {
      relevance = 0.5;
    }
    for (const t of tags) {
      if (contextLower.includes(t.toLowerCase())) relevance = Math.max(relevance, 0.3);
    }

    if (relevance > 0 || triggers.includes(toolName)) {
      matches.push({
        ...p,
        relevance: relevance + p.weight * 0.3 + p.success_rate * 0.2,
        triggerTools: triggers,
        tags,
      });
    }
  }

  // MMR — diversity + relevance
  const selected = [];
  const lambda = 0.7;

  const sorted = matches.sort((a, b) => b.relevance - a.relevance);
  for (const match of sorted) {
    if (selected.length >= 3) break;
    const diversity = selected.length === 0 ? 1 :
      1 - Math.max(...selected.map(s => {
        const sim = countCommon(s.tags, match.tags) / Math.max(s.tags.length + match.tags.length, 1);
        return sim * 2;
      }));
    const score = lambda * match.relevance + (1 - lambda) * diversity;
    if (score > 0.2 || selected.length === 0) {
      selected.push(match);
    }
  }

  return selected;
}

function countCommon(a, b) {
  return a.filter(x => b.includes(x)).length;
}

export function updatePatternSuccess(name, success) {
  const d = getDb();
  if (!d) return;

  const pattern = d.prepare("SELECT * FROM patterns WHERE name = ?").get(name);
  if (!pattern) return;

  const totalUses = d.prepare(
    "SELECT COUNT(*) as c FROM patterns WHERE id = ?"
  ).get(pattern.id);

  // Simplified: just adjust weight
  const newWeight = Math.max(0.1, Math.min(2.0,
    pattern.weight + (success ? 0.1 : -0.2)
  ));
  const newRate = pattern.success_rate === 0.5
    ? (success ? 0.6 : 0.4)
    : (pattern.success_rate * 0.8 + (success ? 0.2 : 0));

  d.prepare("UPDATE patterns SET weight = ?, success_rate = ?, last_used = datetime('now') WHERE id = ?")
    .run(newWeight, newRate, pattern.id);
}

export function getToolDefinition() {
  return {
    name: "openflo_patterns",
    description: "Find matching patterns for a tool and context (MMR-based)",
    inputSchema: {
      type: "object",
      properties: {
        tool: { type: "string", description: "Tool name to find patterns for" },
        context: { type: "string", description: "Current context for relevance matching" },
      },
      required: ["tool"],
    },
  };
}

export function handlePatternQuery(args) {
  const tool = String(args.tool || "").trim();
  if (!tool) throw new (class extends Error {
    constructor() { super("tool is required"); this.code = -32602; this.name = "McpError"; }
  })();

  const matches = findMatchingPatterns(tool, args.context || "");
  if (matches.length === 0) {
    return { content: [{ type: "text", text: `No patterns found for tool "${tool}".` }] };
  }

  const text = matches.map((m, i) =>
    `[${i + 1}] ${m.name} (relevance: ${Math.round(m.relevance * 100)}%, success: ${Math.round(m.success_rate * 100)}%)\n  ${m.description}`
  ).join("\n\n");

  return { content: [{ type: "text", text }] };
}
