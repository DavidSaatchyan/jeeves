import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { load } from "./store.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const DATA_DIR = join(__dirname, "..", "..", ".openflo-data");
const DB_PATH = join(DATA_DIR, "memory.db");

let db = null;

function getDb() {
  if (db) return db;
  try {
    const Database = require("better-sqlite3");
    db = new Database(DB_PATH);
    db.pragma("journal_mode = WAL");
    db.exec(`
      CREATE TABLE IF NOT EXISTS entities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL UNIQUE
      );
      CREATE TABLE IF NOT EXISTS entity_aliases (
        alias TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL REFERENCES entities(id)
      );
      CREATE TABLE IF NOT EXISTS relationships (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL REFERENCES entities(id),
        target_id TEXT NOT NULL REFERENCES entities(id),
        relation_type TEXT NOT NULL,
        metadata TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_rels_source ON relationships(source_id);
      CREATE INDEX IF NOT EXISTS idx_rels_target ON relationships(target_id);
    `);
    return db;
  } catch {
    return null;
  }
}

function normalize(name) {
  return name.toLowerCase().replace(/[-_]/g, "").replace(/[^a-z0-9]/g, "");
}

export function ensureEntity(name) {
  const d = getDb();
  if (!d) return null;
  const normalized = normalize(name);
  let entity = d.prepare("SELECT * FROM entities WHERE normalized_name = ?").get(normalized);
  if (!entity) {
    const id = require("crypto").randomUUID();
    d.prepare("INSERT INTO entities (id, name, normalized_name) VALUES (?, ?, ?)").run(id, name, normalized);
    entity = { id, name, normalized_name: normalized };
  }
  return entity;
}

export function ensureAlias(alias, entityId) {
  const d = getDb();
  if (!d) return;
  d.prepare("INSERT OR IGNORE INTO entity_aliases (alias, entity_id) VALUES (?, ?)").run(alias.toLowerCase(), entityId);
}

export function addRelationship(sourceId, targetId, type, metadata = {}) {
  const d = getDb();
  if (!d) return null;
  const existing = d.prepare(
    "SELECT * FROM relationships WHERE source_id = ? AND target_id = ? AND relation_type = ?"
  ).get(sourceId, targetId, type);
  if (existing) return existing;
  const id = require("crypto").randomUUID();
  d.prepare(
    "INSERT INTO relationships (id, source_id, target_id, relation_type, metadata) VALUES (?, ?, ?, ?, ?)"
  ).run(id, sourceId, targetId, type, JSON.stringify(metadata));
  return { id, source_id: sourceId, target_id: targetId, relation_type: type };
}

export function getEntity(name) {
  const d = getDb();
  if (!d) return null;
  const normalized = normalize(name);
  return d.prepare("SELECT * FROM entities WHERE normalized_name = ?").get(normalized)
    || d.prepare("SELECT e.* FROM entities e JOIN entity_aliases a ON a.entity_id = e.id WHERE a.alias = ?").get(normalized);
}

export function graphQuery(name, depth = 2) {
  const d = getDb();
  if (!d) return { entity: null, relationships: [] };
  const entity = getEntity(name);
  if (!entity) return { entity: null, relationships: [] };

  const visited = new Set();
  const queue = [{ id: entity.id, depth: 0 }];
  const relationships = [];

  while (queue.length > 0) {
    const { id, depth: currentDepth } = queue.shift();
    if (visited.has(id)) continue;
    visited.add(id);

    if (currentDepth >= depth) continue;

    const rels = d.prepare(
      `SELECT r.*, se.name as source_name, te.name as target_name
       FROM relationships r
       JOIN entities se ON se.id = r.source_id
       JOIN entities te ON te.id = r.target_id
       WHERE r.source_id = ? OR r.target_id = ?`
    ).all(id, id);

    for (const rel of rels) {
      relationships.push(rel);
      const otherId = rel.source_id === id ? rel.target_id : rel.source_id;
      if (!visited.has(otherId)) {
        queue.push({ id: otherId, depth: currentDepth + 1 });
      }
    }
  }

  return { entity, relationships };
}

export function discoverFromMemories() {
  const d = getDb();
  if (!d) return 0;
  const memories = load();
  let count = 0;

  for (const mem of memories) {
    // Extract entities from key (e.g., "billing:stripe-choice" → "billing", "stripe")
    const keyParts = mem.key.split(/[:-]/);
    const entities = [];

    for (const part of keyParts) {
      const clean = part.replace(/[^a-zA-Z0-9]/g, "");
      if (clean.length >= 3) entities.push(clean);
    }

    // Extract PascalCase entities from content
    const pascals = mem.content.match(/[A-Z][a-z]+(?:[A-Z][a-z]+)+/g) || [];
    for (const p of pascals) {
      if (p.length >= 4) entities.push(p);
    }

    // Create entities and link to memory
    for (let i = 0; i < entities.length; i++) {
      const e1 = ensureEntity(entities[i]);
      if (!e1) continue;
      addRelationship(e1.id, e1.id, "self", { memoryKey: mem.key });
      count++;

      // Link adjacent entities from same memory
      if (i < entities.length - 1) {
        const e2 = ensureEntity(entities[i + 1]);
        if (e2) {
          addRelationship(e1.id, e2.id, "co-occurs", { memoryKey: mem.key });
        }
      }
    }

    // Add memory key as alias
    if (entities.length > 0 && entities[0]) {
      const e = getEntity(entities[0]);
      if (e) ensureAlias(mem.key, e.id);
    }
  }

  return count;
}

export function getToolDefinition() {
  return {
    name: "openflo_graph",
    description: "Query entity relationships in the knowledge graph",
    inputSchema: {
      type: "object",
      properties: {
        entity: { type: "string", description: "Entity name to query" },
        depth: { type: "number", description: "Relationship depth (1-5)", default: 2 },
      },
      required: ["entity"],
    },
  };
}

export function handleGraphQuery(args) {
  const entity = String(args.entity || "").trim();
  const depth = Math.min(Math.max(1, args.depth || 2), 5);

  if (!entity) {
    return { content: [{ type: "text", text: "Entity name required." }] };
  }

  const result = graphQuery(entity, depth);

  if (!result.entity) {
    // Auto-discover might help
    const discovered = discoverFromMemories();
    const retry = graphQuery(entity, depth);
    if (retry.entity) {
      return formatGraphResult(retry, discovered);
    }
    return { content: [{ type: "text", text: `Entity "${entity}" not found. Try openflo_graph_discover to build the graph.` }] };
  }

  return formatGraphResult(result, 0);
}

export function getDiscoverToolDef() {
  return {
    name: "openflo_graph_discover",
    description: "Scan memories to discover entities and build the knowledge graph",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max memories to scan", default: 200 },
      },
    },
  };
}

export function handleDiscover(args) {
  const count = discoverFromMemories();
  const d = getDb();
  const entityCount = d ? d.prepare("SELECT COUNT(*) as c FROM entities").get().c : 0;
  const relCount = d ? d.prepare("SELECT COUNT(*) as c FROM relationships").get().c : 0;
  return {
    content: [{
      type: "text",
      text: `Graph build: ${count} relationships discovered.\nEntities: ${entityCount}\nRelationships: ${relCount}`,
    }],
  };
}

function formatGraphResult(result, newDiscoveries) {
  const lines = [
    `Entity: ${result.entity.name}`,
    `Relationships (${result.relationships.length}):`,
  ];

  const seen = new Set();
  for (const rel of result.relationships) {
    const key = `${rel.source_id}-${rel.target_id}-${rel.relation_type}`;
    if (seen.has(key)) continue;
    seen.add(key);

    if (rel.source_id === rel.target_id) {
      lines.push(`  self: memory "${JSON.parse(rel.metadata || "{}").memoryKey || "unknown"}"`);
    } else if (rel.relation_type === "co-occurs") {
      const other = rel.source_id === result.entity.id ? rel.target_name : rel.source_name;
      lines.push(`  co-occurs with "${other}" via "${JSON.parse(rel.metadata || "{}").memoryKey || "unknown"}"`);
    } else {
      lines.push(`  [${rel.relation_type}] ${rel.source_name} → ${rel.target_name}`);
    }
  }

  if (newDiscoveries > 0) {
    lines.push(`\n(Discovered ${newDiscoveries} new relationships during query)`);
  }

  return { content: [{ type: "text", text: lines.join("\n") }] };
}
