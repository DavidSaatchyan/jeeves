import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createMemory, load } from "./store.js";

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
      CREATE TABLE IF NOT EXISTS votes (
        id TEXT PRIMARY KEY,
        topic TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        vote TEXT NOT NULL CHECK(vote IN ('approve','reject','abstain')),
        reasoning TEXT,
        confidence REAL DEFAULT 0.5,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_votes_topic ON votes(topic);
    `);
    return db;
  } catch { return null; }
}

export function castVote(topic, agentName, vote, { reasoning, confidence } = {}) {
  const d = getDb();
  if (!d) return null;

  // Remove previous vote from same agent on same topic
  d.prepare("DELETE FROM votes WHERE topic = ? AND agent_name = ?").run(topic, agentName);

  const id = require("crypto").randomUUID();
  d.prepare("INSERT INTO votes (id, topic, agent_name, vote, reasoning, confidence) VALUES (?, ?, ?, ?, ?, ?)")
    .run(id, topic, agentName, vote, reasoning || null, confidence || 0.5);

  // Store in memory for cross-session recall
  createMemory(
    `consensus:${topic}:${agentName}`,
    `Vote on "${topic}": ${vote} (confidence: ${confidence || 0.5})${reasoning ? ` — ${reasoning}` : ""}`,
    ["consensus", "vote", vote, topic]
  );

  return { id, topic, agentName, vote };
}

export function tallyVotes(topic) {
  const d = getDb();
  if (!d) return { topic, votes: [], consensus: null };

  const votes = d.prepare("SELECT * FROM votes WHERE topic = ? ORDER BY created_at DESC").all(topic);
  if (votes.length === 0) return { topic, votes: [], consensus: null };

  const tally = { approve: 0, reject: 0, abstain: 0 };
  let weightedApprove = 0;
  let weightedTotal = 0;

  for (const v of votes) {
    tally[v.vote]++;
    if (v.vote === "approve") weightedApprove += v.confidence;
    if (v.vote === "reject") weightedApprove -= v.confidence;
    weightedTotal += v.confidence;
  }

  const approvalRatio = weightedTotal > 0 ? weightedApprove / weightedTotal : 0;

  // Consensus rules
  let consensus;
  if (approvalRatio >= 0.6) consensus = "approved";
  else if (approvalRatio <= -0.4) consensus = "rejected";
  else if (votes.length >= 3 && Math.abs(approvalRatio) < 0.2) consensus = "needs-discussion";
  else consensus = "undecided";

  return {
    topic,
    totalVotes: votes.length,
    tally,
    approvalRatio: Math.round(approvalRatio * 100) / 100,
    consensus,
    votes: votes.map(v => ({
      agent: v.agent_name,
      vote: v.vote,
      reasoning: v.reasoning,
      confidence: v.confidence,
    })),
  };
}

export function getToolDefinitions() {
  return [
    {
      name: "openflo_consensus_vote",
      description: "Cast a vote on a decision topic (approve/reject/abstain)",
      inputSchema: {
        type: "object",
        properties: {
          topic: { type: "string", description: "Decision topic (e.g., 'use-stripe-vs-paddle')" },
          agent: { type: "string", description: "Your agent name" },
          vote: { type: "string", enum: ["approve", "reject", "abstain"] },
          reasoning: { type: "string", description: "Why this vote" },
          confidence: { type: "number", description: "Confidence 0-1", default: 0.5 },
        },
        required: ["topic", "agent", "vote"],
      },
    },
    {
      name: "openflo_consensus_tally",
      description: "Tally votes for a topic and determine consensus",
      inputSchema: {
        type: "object",
        properties: {
          topic: { type: "string", description: "Topic to tally" },
        },
        required: ["topic"],
      },
    },
  ];
}

export function handleConsensusTool(name, args) {
  switch (name) {
    case "openflo_consensus_vote": {
      if (!args?.topic || !args?.agent || !args?.vote) throw mcpError(-32602, "topic, agent, vote required");
      if (!["approve", "reject", "abstain"].includes(args.vote)) throw mcpError(-32602, "vote must be approve/reject/abstain");

      const result = castVote(args.topic, args.agent, args.vote, {
        reasoning: args.reasoning,
        confidence: args.confidence || 0.5,
      });

      return { content: [{ type: "text", text: `${args.agent} voted ${args.vote} on "${args.topic}".` }] };
    }

    case "openflo_consensus_tally": {
      if (!args?.topic) throw mcpError(-32602, "topic required");

      const result = tallyVotes(args.topic);
      if (result.votes.length === 0) {
        return { content: [{ type: "text", text: `No votes yet on "${args.topic}".` }] };
      }

      const lines = [
        `Consensus: "${args.topic}"`,
        `  Status: ${result.consensus}`,
        `  Approval ratio: ${result.approvalRatio}`,
        `  Votes: ${result.tally.approve} approve, ${result.tally.reject} reject, ${result.tally.abstain} abstain`,
        `\nDetails:`,
      ];
      for (const v of result.votes) {
        lines.push(`  ${v.agent}: ${v.vote} (confidence: ${v.confidence})${v.reasoning ? ` — ${v.reasoning}` : ""}`);
      }

      return { content: [{ type: "text", text: lines.join("\n") }] };
    }

    default:
      throw mcpError(-32601, `Tool not found: ${name}`);
  }
}

function mcpError(code, message) {
  const err = new Error(message);
  err.code = code;
  err.name = "McpError";
  return err;
}
