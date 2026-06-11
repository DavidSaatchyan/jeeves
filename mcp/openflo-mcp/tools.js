import { load, createMemory, deleteMemory, getMemory, getStats, listTags } from "./store.js";
import { searchMemories } from "./search.js";
import { getToolDefinition as getPIIDef, handlePIIScan } from "./pii.js";
import { getToolDefinition as getMetricsDef, handleMetrics } from "./metrics.js";
import { semanticSearch, addEmbedding, isVectorMode } from "./backends/vector.js";
import { getToolDefinition as getGraphDef, handleGraphQuery, getDiscoverToolDef, handleDiscover } from "./graph.js";
import { getToolDefinition as getBridgeDef, handleBridge } from "./bridge.js";
import { getToolDefinition as getPatternsDef, handlePatternQuery } from "./patterns.js";
import { getToolDefinition as getReasoningDef, handleReasoningQuery } from "./reasoning.js";
import { getToolDefinitions as getGoalDefs, handleGoalTool } from "./goals.js";
import { getToolDefinitions as getConsensusDefs, handleConsensusTool } from "./consensus.js";
import { Logger } from "./logger.js";
import path from "node:path";

// Lazy federation tool definitions (imported on first use, not at module load)
const _fedTools = [
  {
    name: "openflo_federation_peers",
    description: "List known federation peers with trust scores",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "openflo_federation_send",
    description: "Prepare a signed message for a peer (PII-scanned before sending)",
    inputSchema: {
      type: "object",
      properties: {
        target: { type: "string", description: "Target peer ID" },
        type: { type: "string", enum: ["task_request", "task_response", "sync_memory", "heartbeat"] },
        payload: { type: "object", description: "Message payload" },
      },
      required: ["target", "type", "payload"],
    },
  },
  {
    name: "openflo_federation_status",
    description: "Get federation identity and queue status",
    inputSchema: { type: "object", properties: {} },
  },
];
let _fedHandler = null;
async function getFedHandler() {
  if (!_fedHandler) {
    const mod = await import("../openflo-federation/task.js");
    _fedHandler = mod.handleFederationTool;
  }
  return _fedHandler;
}

export const toolDefinitions = [
  getPIIDef(),
  getMetricsDef(),
  getGraphDef(),
  getDiscoverToolDef(),
  getBridgeDef(),
  getPatternsDef(),
  getReasoningDef(),
  ...getGoalDefs(),
  ...getConsensusDefs(),
  ..._fedTools,
  {
    name: "openflo_design_system",
    description: "Generate a complete design system (style, colors, typography, effects) for a product type. Uses data-driven search across 49 styles, 43 color palettes, 45 font pairings, and 51 product types.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Product type and keywords (e.g., 'fintech crypto banking')" },
        project: { type: "string", description: "Optional project name for output header" },
        format: { type: "string", enum: ["ascii", "json"], description: "Output format", default: "ascii" },
      },
      required: ["query"],
    },
  },
  {
    name: "openflo_skill_search",
    description: "Search skill knowledge data by domain. Domains: styles (49 UI styles), colors (43 palettes), fonts (45 pairings), products (51 product types), ux-rules (80+ UX rules), charts (20 chart types).",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search keywords (e.g., 'glassmorphism dark' or 'form validation')" },
        domain: { type: "string", enum: ["styles", "colors", "fonts", "products", "ux-rules", "charts"], description: "Data domain to search" },
        limit: { type: "number", description: "Max results (1-10)", default: 5 },
        format: { type: "string", enum: ["ascii", "json"], description: "Output format", default: "ascii" },
      },
      required: ["query", "domain"],
    },
  },
  {
    name: "openflo_logs",
    description: "Query server logs by level, component, and limit",
    inputSchema: {
      type: "object",
      properties: {
        level: { type: "string", enum: ["DEBUG", "INFO", "WARN", "ERROR"], description: "Minimum log level" },
        component: { type: "string", description: "Filter by component name" },
        limit: { type: "number", description: "Max log entries (1-500)", default: 50 },
        since: { type: "string", description: "ISO timestamp, only show entries after this time" },
      },
    },
  },
  {
    name: "openflo_recall",
    description: "Search stored memories by query string, semantic similarity, tag, or key",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query (supports multi-word)" },
        tag: { type: "string", description: "Filter by tag" },
        key: { type: "string", description: "Exact key match" },
        mode: {
          type: "string",
          enum: ["keyword", "semantic"],
          description: "keyword (default, substring+fuzzy) or semantic (vector embeddings)",
          default: "keyword",
        },
        fuzzy: { type: "boolean", description: "Enable fuzzy/typo-tolerant search", default: false },
        limit: { type: "number", description: "Max results (1-50)", default: 10 },
      },
    },
  },
  {
    name: "openflo_learn",
    description: "Store a fact, decision, or pattern for future sessions",
    inputSchema: {
      type: "object",
      properties: {
        key: { type: "string", description: "Unique identifier for this memory (e.g., 'billing:stripe-choice')" },
        content: { type: "string", description: "The memory content" },
        tags: {
          type: "array",
          items: { type: "string" },
          description: "Tags for categorization (e.g., ['architecture', 'billing'])",
        },
      },
      required: ["key", "content"],
    },
  },
  {
    name: "openflo_forget",
    description: "Remove a stored memory by its ID",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Memory ID to remove" },
      },
      required: ["id"],
    },
  },
  {
    name: "openflo_list_tags",
    description: "List all tags used in memory, sorted by frequency",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "openflo_stats",
    description: "Get memory storage statistics (count, usage, tag distribution)",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
];

export async function handleToolCall(name, args) {
  switch (name) {
    case "openflo_recall": {
      const limit = Math.min(Math.max(1, args.limit || 10), 50);

      if (args.mode === "semantic") {
        const { initVectorSearch } = await import("./backends/vector.js");
        await initVectorSearch();
        const results = await semanticSearch(args.query || "", {
          tag: args.tag,
          key: args.key,
          limit,
        });
        if (results.length === 0) {
          return { content: [{ type: "text", text: "No semantic matches found. Try keyword mode." }] };
        }
        const text = results.map(m =>
          `[${m.id}] ${m.key}: ${m.content}\n  score: ${m.score} | created: ${m.createdAt} | tags: ${(m.tags || []).join(", ") || "none"}`
        ).join("\n\n");
        return { content: [{ type: "text", text }] };
      }

      const memories = load();
      const results = searchMemories(memories, args.query || "", {
        tag: args.tag,
        key: args.key,
        fuzzy: args.fuzzy === true,
        limit,
      });
      if (results.length === 0) {
        return { content: [{ type: "text", text: "No memories found." }] };
      }
      const text = results.map(m =>
        `[${m.id}] ${m.key}: ${m.content}\n  created: ${m.createdAt} | tags: ${(m.tags || []).join(", ") || "none"}`
      ).join("\n\n");
      return { content: [{ type: "text", text }] };
    }

    case "openflo_learn": {
      if (!args?.key || !args?.content) {
        throw new McpError(-32602, "key and content are required");
      }
      const key = String(args.key).trim();
      const content = String(args.content).trim();
      const memory = createMemory(key, content, args.tags);
      await addEmbedding(memory.id, content);
      return { content: [{ type: "text", text: `Stored: "${key}" (id: ${memory.id})` }] };
    }

    case "openflo_forget": {
      const ok = deleteMemory(args.id);
      if (!ok) {
        return { content: [{ type: "text", text: `No memory found with id "${args.id}"` }] };
      }
      return { content: [{ type: "text", text: `Forgot memory "${args.id}"` }] };
    }

    case "openflo_list_tags": {
      const tags = listTags();
      if (tags.length === 0) {
        return { content: [{ type: "text", text: "No tags found." }] };
      }
      const text = tags.map(t => `${t.tag}: ${t.count}`).join("\n");
      return { content: [{ type: "text", text }] };
    }

    case "openflo_stats": {
      const stats = getStats();
      const lines = [
        `Total memories: ${stats.total} / ${stats.max} (${stats.usagePercent}%)`,
        `Unique keys: ${stats.uniqueKeys}`,
        `Unique tags: ${stats.uniqueTags}`,
        `Oldest: ${stats.oldest || "N/A"}`,
        `Newest: ${stats.newest || "N/A"}`,
        "",
        "Tags by frequency:",
        ...stats.tagCounts ? Object.entries(stats.tagCounts)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 20)
          .map(([tag, count]) => `  ${tag}: ${count}`) : ["  (none)"],
      ];
      return { content: [{ type: "text", text: lines.join("\n") }] };
    }

    case "openflo_pii_scan": {
      return handlePIIScan(args);
    }

    case "openflo_metrics": {
      return handleMetrics(args);
    }

    case "openflo_graph": {
      if (!args?.entity) throw new McpError(-32602, "entity is required");
      return handleGraphQuery(args);
    }

    case "openflo_graph_discover": {
      return handleDiscover(args);
    }

    case "openflo_bridge": {
      return handleBridge(args);
    }

    case "openflo_patterns": {
      return handlePatternQuery(args);
    }

    case "openflo_reasoning": {
      return handleReasoningQuery(args);
    }

    case "openflo_goal_save":
    case "openflo_goal_load":
    case "openflo_goal_status":
    case "openflo_goal_replan": {
      return handleGoalTool(name, args);
    }

    case "openflo_consensus_vote":
    case "openflo_consensus_tally": {
      return handleConsensusTool(name, args);
    }

    case "openflo_federation_peers":
    case "openflo_federation_send":
    case "openflo_federation_status": {
      const fedHandler = await getFedHandler();
      return fedHandler(name, args);
    }

    case "openflo_design_system": {
      const { SkillEngine } = await import("../../.opencode/skills/shared/engine.js");
      const skillDir = path.join(process.cwd(), ".opencode", "skills", "ux-designer");
      const engine = new SkillEngine(skillDir);
      const ds = engine.designSystem(args.query || "", args.project || "Untitled");
      if (args.format === "json") {
        return { content: [{ type: "text", text: JSON.stringify(ds, null, 2) }] };
      }
      const lines = [];
      lines.push("+----------------------------------------------------------------------------------------+");
      lines.push(`|  PROJECT: ${ds.project.padEnd(74)}|`);
      lines.push("+----------------------------------------------------------------------------------------+");
      lines.push(`|  PATTERN: ${(ds.pattern || "").padEnd(64)}|`);
      lines.push(`|  Product Type: ${(ds.productType || "").padEnd(60)}|`);
      lines.push("|                                                                                        |");
      lines.push(`|  STYLE: ${(ds.style?.name || "").padEnd(67)}|`);
      if (ds.style?.description) lines.push(`|  ${ds.style.description.padEnd(87)}|`);
      lines.push("|                                                                                        |");
      if (ds.colors) {
        lines.push("|  COLORS:");
        lines.push(`|     Primary:    ${(ds.colors.primary || "").padEnd(68)}|`);
        lines.push(`|     Secondary:  ${(ds.colors.secondary || "").padEnd(68)}|`);
        lines.push(`|     Background: ${(ds.colors.background || "").padEnd(68)}|`);
        lines.push(`|     Text:       ${(ds.colors.text || "").padEnd(68)}|`);
      }
      lines.push("|                                                                                        |");
      if (ds.typography) {
        lines.push(`|  TYPOGRAPHY: ${(ds.typography.headings || "")} / ${(ds.typography.body || "")}`);
        if (ds.typography.mood) lines.push(`|  Mood: ${ds.typography.mood.padEnd(80)}`);
      }
      lines.push("|                                                                                        |");
      lines.push(`|  KEY EFFECTS: ${(ds.effects || "").padEnd(66)}|`);
      lines.push("|                                                                                        |");
      lines.push("|  AVOID (Anti-patterns):");
      (ds.antiPatterns || []).forEach(ap => lines.push(`|     - ${ap.padEnd(72)}|`));
      lines.push("|                                                                                        |");
      lines.push("|  PRE-DELIVERY CHECKLIST:");
      (ds.checklist || []).forEach((item, i) => lines.push(`|     [${i+1}] ${item.padEnd(68)}|`));
      lines.push("+----------------------------------------------------------------------------------------+");
      return { content: [{ type: "text", text: lines.join("\n") }] };
    }

    case "openflo_skill_search": {
      const { SkillEngine: SE } = await import("../../.opencode/skills/shared/engine.js");
      const sDir = path.join(process.cwd(), ".opencode", "skills", "ux-designer");
      const eng = new SE(sDir);
      const results = eng.search(args.domain, args.query || "", { limit: args.limit || 5 });
      if (results.length === 0) {
        return { content: [{ type: "text", text: `No results found for "${args.query}" in ${args.domain}.` }] };
      }
      if (args.format === "json") {
        return { content: [{ type: "text", text: JSON.stringify(results, null, 2) }] };
      }
      const parts = results.map((r, i) => {
        const lines = [`\nResult ${i + 1} (score: ${r._score.toFixed(2)})`];
        if (r.name) lines.push(`Name: ${r.name}`);
        if (r.description) lines.push(`Description: ${r.description}`);
        if (r.bestFor) lines.push(`Best For: ${r.bestFor}`);
        if (r.dos) lines.push(`Do: ${r.dos}`);
        if (r.donts) lines.push(`Don't: ${r.donts}`);
        if (r.priority) lines.push(`Priority: ${r.priority}`);
        if (r.mood) lines.push(`Mood: ${r.mood}`);
        return lines.join("\n");
      });
      return { content: [{ type: "text", text: parts.join("\n" + "=".repeat(60)) }] };
    }

    case "openflo_logs": {
      const limit = Math.min(Math.max(1, args.limit || 50), 500);
      const entries = Logger.readLogs({ level: args.level, component: args.component, limit, since: args.since });
      if (entries.length === 0) {
        return { content: [{ type: "text", text: "No log entries match the filters." }] };
      }
      const text = entries.map(e =>
        `[${e.timestamp}] [${e.level}] ${e.component}: ${e.message}${e.metadata && Object.keys(e.metadata).length ? " " + JSON.stringify(e.metadata) : ""}`
      ).join("\n");
      return { content: [{ type: "text", text }] };
    }

    default:
      throw new McpError(-32601, `Tool not found: ${name}`);
  }
}

class McpError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
    this.name = "McpError";
  }
}
