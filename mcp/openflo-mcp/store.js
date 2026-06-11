import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

let sqlite;
try {
  sqlite = await import("./backends/sqlite.js");
} catch (err) {
  process.stderr.write(`[openflo-mcp] SQLite backend unavailable: ${err.message}\n`);
  process.stderr.write(`[openflo-mcp] Falling back to JSON file backend\n`);
  // Dynamic fallback — will use a simplified JSON store
  const { readFileSync, writeFileSync, mkdirSync } = await import("node:fs");
  const crypto = await import("node:crypto");
  const DATA_DIR = join(__dirname, "..", "..", ".openflo-data");
  const MEMORY_FILE = join(DATA_DIR, "memory.json");
  const MAX_MEMORIES = 10_000;
  if (!existsSync(DATA_DIR)) mkdirSync(DATA_DIR, { recursive: true });

  sqlite = {
    load() {
      if (!existsSync(MEMORY_FILE)) return [];
      try { return JSON.parse(readFileSync(MEMORY_FILE, "utf-8")); } catch { return []; }
    },
    createMemory(key, content, tags = []) {
      const memories = this.load();
      if (memories.length >= MAX_MEMORIES) {
        memories.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
        memories.splice(0, memories.length - MAX_MEMORIES + 1);
      }
      const memory = {
        id: crypto.randomUUID(),
        key, content,
        tags: [...new Set((tags || []).map(t => String(t).toLowerCase()))],
        createdAt: new Date().toISOString(),
      };
      memories.push(memory);
      writeFileSync(MEMORY_FILE, JSON.stringify(memories, null, 2));
      return memory;
    },
    deleteMemory(id) {
      const memories = this.load();
      const idx = memories.findIndex(m => m.id === id);
      if (idx === -1) return false;
      memories.splice(idx, 1);
      writeFileSync(MEMORY_FILE, JSON.stringify(memories, null, 2));
      return true;
    },
    getMemory(id) { return this.load().find(m => m.id === id) || null; },
    getStats() {
      const memories = this.load();
      const tagCounts = {};
      for (const m of memories) for (const t of m.tags) tagCounts[t] = (tagCounts[t] || 0) + 1;
      return {
        total: memories.length, max: MAX_MEMORIES,
        usagePercent: Math.round((memories.length / MAX_MEMORIES) * 100),
        uniqueKeys: new Set(memories.map(m => m.key)).size,
        uniqueTags: Object.keys(tagCounts).length,
        tagCounts, entriesByDay: {},
        oldest: memories[memories.length - 1]?.createdAt || null,
        newest: memories[0]?.createdAt || null,
      };
    },
    listTags() {
      const counts = {};
      for (const m of this.load()) for (const t of m.tags) counts[t] = (counts[t] || 0) + 1;
      return Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([tag, count]) => ({ tag, count }));
    },
  };
}

// Auto-import existing JSON data on first run
const JSON_PATH = join(__dirname, "..", "..", ".openflo-data", "memory.json");
try {
  if (sqlite.importFromJson && existsSync(JSON_PATH)) {
    const count = sqlite.importFromJson(JSON_PATH);
    if (count > 0) {
      process.stderr.write(`[openflo-mcp] Imported ${count} memories from JSON\n`);
    }
    // Rename old JSON file after import to prevent re-import
    const { renameSync } = await import("node:fs");
    try { renameSync(JSON_PATH, JSON_PATH + ".imported"); } catch {}
  }
} catch {}

export const load = sqlite.load.bind(sqlite);
export const createMemory = sqlite.createMemory.bind(sqlite);
export const deleteMemory = sqlite.deleteMemory.bind(sqlite);
export const getMemory = sqlite.getMemory.bind(sqlite);
export const getStats = sqlite.getStats.bind(sqlite);
export const listTags = sqlite.listTags.bind(sqlite);
