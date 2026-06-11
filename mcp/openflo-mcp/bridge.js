import { existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { createMemory, load } from "./store.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

function scanMarkdownFiles(dir) {
  const results = [];
  if (!existsSync(dir)) return results;
  try {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isFile() && (entry.name.endsWith(".md") || entry.name.endsWith(".json"))) {
        const fullPath = join(dir, entry.name);
        try {
          const content = readFileSync(fullPath, "utf-8").trim();
          if (content.length > 20) {
            results.push({
              path: fullPath,
              content: content.slice(0, 5000),
              source: entry.name.endsWith(".json") ? "json" : "markdown",
            });
          }
        } catch {}
      }
    }
  } catch {}
  return results;
}

function scanOpenCodeMemory() {
  const base = join(homedir(), ".opencode", "memory");
  return scanMarkdownFiles(base).map(r => ({ ...r, origin: "opencode" }));
}

function scanClaudeMemory() {
  const results = [];
  const projectsDir = join(homedir(), ".claude", "projects");
  if (!existsSync(projectsDir)) return results;
  try {
    for (const proj of readdirSync(projectsDir, { withFileTypes: true })) {
      if (proj.isDirectory()) {
        const memoryDir = join(projectsDir, proj.name, "memory");
        const files = scanMarkdownFiles(memoryDir);
        for (const f of files) {
          results.push({ ...f, origin: `claude:${proj.name}` });
        }
      }
    }
  } catch {}
  return results;
}

function scanSiblingProjects() {
  const results = [];
  const currentDir = join(__dirname, "..", "..");
  try {
    const parent = dirname(currentDir);
    for (const entry of readdirSync(parent, { withFileTypes: true })) {
      if (!entry.isDirectory() || entry.name.startsWith(".") || entry.name === basename(currentDir)) continue;
      const jsonPath = join(parent, entry.name, ".openflo-data", "memory.json");
      const jsonPath2 = join(parent, entry.name, ".opencode-data", "memory.json");
      for (const p of [jsonPath, jsonPath2]) {
        if (existsSync(p)) {
          try {
            const data = JSON.parse(readFileSync(p, "utf-8"));
            if (Array.isArray(data)) {
              for (const mem of data) {
                if (mem.key && mem.content) {
                  results.push({
                    key: mem.key,
                    content: mem.content.slice(0, 5000),
                    tags: [...(mem.tags || []), `bridge:${entry.name}`],
                    origin: `project:${entry.name}`,
                  });
                }
              }
            }
          } catch {}
        }
      }
    }
  } catch {}
  return results;
}

export function bridge(options = {}) {
  const { sources = ["opencode", "claude", "siblings"], dryRun = false } = options;
  const imported = { opencode: 0, claude: 0, siblings: 0, skipped: 0 };
  const existingKeys = new Set(load().map(m => m.key));

  // Scan OpenCode memory
  if (sources.includes("opencode")) {
    for (const file of scanOpenCodeMemory()) {
      const key = `bridge:opencode:${basename(file.path).replace(/\.(md|json)$/, "")}`;
      if (!existingKeys.has(key)) {
        if (!dryRun) createMemory(key, file.content, ["bridge", "opencode", file.origin]);
        imported.opencode++;
        existingKeys.add(key);
      } else {
        imported.skipped++;
      }
    }
  }

  // Scan Claude Code memory
  if (sources.includes("claude")) {
    for (const file of scanClaudeMemory()) {
      const key = `bridge:${file.origin.replace(":", "-")}:${basename(file.path).replace(/\.(md|json)$/, "")}`;
      if (!existingKeys.has(key)) {
        if (!dryRun) createMemory(key, file.content, ["bridge", "claude", file.origin]);
        imported.claude++;
        existingKeys.add(key);
      } else {
        imported.skipped++;
      }
    }
  }

  // Scan sibling projects
  if (sources.includes("siblings")) {
    for (const mem of scanSiblingProjects()) {
      if (!existingKeys.has(mem.key)) {
        if (!dryRun) createMemory(mem.key, mem.content, mem.tags);
        imported.siblings++;
        existingKeys.add(mem.key);
      } else {
        imported.skipped++;
      }
    }
  }

  return imported;
}

export function getToolDefinition() {
  return {
    name: "openflo_bridge",
    description: "Import memories from OpenCode, Claude Code, and sibling projects",
    inputSchema: {
      type: "object",
      properties: {
        sources: {
          type: "array",
          items: { type: "string", enum: ["opencode", "claude", "siblings"] },
          description: "Sources to scan (default: all)",
        },
        dryRun: {
          type: "boolean",
          description: "If true, only count without importing",
          default: false,
        },
      },
    },
  };
}

export function handleBridge(args) {
  const result = bridge({
    sources: args.sources || ["opencode", "claude", "siblings"],
    dryRun: args.dryRun === true,
  });

  const lines = [
    "Bridge Import Results:",
    `  OpenCode memory: ${result.opencode} imported`,
    `  Claude Code memory: ${result.claude} imported`,
    `  Sibling projects: ${result.siblings} imported`,
    `  Skipped (duplicates): ${result.skipped}`,
    args.dryRun ? "\n(Dry run — no changes made)" : "",
  ];

  return { content: [{ type: "text", text: lines.filter(Boolean).join("\n") }] };
}
