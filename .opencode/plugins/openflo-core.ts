import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import type { Plugin } from "@opencode-ai/plugin";

const __dirname = dirname(new URL(import.meta.url).pathname);
const CONFIG_PATH = join(__dirname, "..", "..", "opencode.json");

class PluginError extends Error {
  constructor(
    message: string,
    public code: string,
    public recoverable: boolean,
    public retryCount?: number
  ) { super(message); }
}

function recordTrajectory(toolName: string, args: unknown, success: boolean, durationMs?: number) {
  try {
    const reasoning =
      `Tool ${toolName} ${success ? "succeeded" : "failed"} ` +
      `with args: ${JSON.stringify(args).slice(0, 200)}`;
    // Store in memory as trajectory (MCP tool not available from plugins,
    // so we use memory directly)
    console.log(
      `[trajectory] ${toolName} ${success ? "OK" : "FAIL"} (${durationMs || "?"}ms): ${reasoning.slice(0, 100)}`
    );
  } catch {}
}

function suggestTestFile(sourcePath: string): string | null {
  const testMappings: Array<{ srcPattern: RegExp; testPath: string }> = [
    { srcPattern: /^src[\\\/](.+)\.ts$/, testPath: "tests/$1.test.ts" },
    { srcPattern: /^src[\\\/](.+)\.tsx$/, testPath: "tests/$1.test.tsx" },
    { srcPattern: /^src[\\\/](.+)\.js$/, testPath: "tests/$1.test.js" },
    { srcPattern: /^src[\\\/](.+)\.jsx$/, testPath: "tests/$1.test.jsx" },
    { srcPattern: /^packages[\\\/](.+?)\.ts$/, testPath: "packages/__tests__/$1.test.ts" },
    { srcPattern: /^app[\\\/](.+?)\.tsx?$/, testPath: "__tests__/$1.test.tsx" },
    { srcPattern: /^lib[\\\/](.+?)\.rb$/, testPath: "spec/$1_spec.rb" },
    { srcPattern: /^lib[\\\/](.+?)\.py$/, testPath: "tests/test_$1.py" },
    { srcPattern: /^src[\\\/](.+?)\.go$/, testPath: "src/$1_test.go" },
  ];
  for (const { srcPattern, testPath } of testMappings) {
    const match = sourcePath.match(srcPattern);
    if (match) return testPath.replace("$1", match[1]);
  }
  return null;
}

function getErrorCode(error: unknown): string {
  if (error instanceof PluginError) return error.code;
  if (error instanceof Error) {
    if (error.message.includes("timeout")) return "E_TIMEOUT";
    if (error.message.includes("permission")) return "E_PERMISSION";
    if (error.message.includes("MCP") || error.message.includes("mcp")) return "E_MCP";
  }
  return "E_UNKNOWN";
}

function safeLog(level: string, msg: string, data?: unknown) {
  try {
    console.log(`[openflo-core] ${level}: ${msg}`, data ? JSON.stringify(data) : "");
  } catch { }
}

export default (async ({ client }) => {
  const state: { initialized: boolean; mcpAvailable: boolean; config: Record<string, unknown> } = {
    initialized: false,
    mcpAvailable: true,
    config: {},
  };

  return {
    config: async (config: Record<string, unknown>) => {
      state.config = config;
      const agents = config?.agents as Record<string, unknown> | undefined;
      if (!agents || !agents.swarm) {
        safeLog("warn", "OpenFlo: no swarm agent found in config");
      }
    },

    "chat.message": async (message: { text?: string }) => {
      const text = message?.text || "";
      if (!text.startsWith("/agents") && !text.startsWith("/agent ")) return;

      const agents = (state.config?.agents as Record<string, unknown>) || {};
      const agentNames = Object.keys(agents);

      if (text === "/agents list") {
        const lines = ["Available agents:"];
        for (const name of agentNames) {
          const a = agents[name] as Record<string, unknown> || {};
          lines.push(`  ${name} — ${a.description || "no description"} [${a.model || "?"}]`);
        }
        safeLog("info", lines.join("\n"));
        return;
      }

      if (text.startsWith("/agent ")) {
        const rest = text.slice(7).trim();
        const spaceIdx = rest.indexOf(" ");
        const agentName = spaceIdx > 0 ? rest.slice(0, spaceIdx) : rest;
        const taskDesc = spaceIdx > 0 ? rest.slice(spaceIdx + 1) : "";
        if (!agentNames.includes(agentName)) {
          safeLog("warn", `Agent not found: ${agentName}`);
          return;
        }
        safeLog("info", `Agent ${agentName} selected for: ${taskDesc}`);
        return;
      }

      if (text.startsWith("/agents suggest ")) {
        const task = text.slice(16).trim();
        if (!task) { safeLog("warn", "Usage: /agents suggest <task description>"); return; }
        const scored = agentNames.map((name) => {
          const a = agents[name] as Record<string, unknown> || {};
          const desc = (a.description as string) || "";
          let score = 0;
          const keywords = task.toLowerCase().split(/\s+/);
          for (const kw of keywords) {
            if (desc.toLowerCase().includes(kw)) score += 2;
            if (name.includes(kw)) score += 3;
          }
          return { name, score, description: desc };
        }).filter(s => s.score > 0).sort((a, b) => b.score - a.score);
        if (scored.length === 0) {
          safeLog("info", `No agents match "${task}". Try: ${agentNames.slice(0, 5).join(", ")}`);
          return;
        }
        safeLog("info", `Recommendation for "${task}":\n${scored.slice(0, 3).map(s => `  ${s.name} (score: ${s.score}) — ${s.description}`).join("\n")}`);
      }
    },

    "tool.execute.before": async (input: { name: string; args: Record<string, unknown> }) => {
      if (input.name === "openflo_learn") {
        const key = input.args?.key as string | undefined;
        if (!key || typeof key !== "string" || key.trim().length === 0) {
          throw new PluginError("Invalid learn key", "E_INVALID_INPUT", false);
        }
      }
      if (input.name === "openflo_recall" && !state.mcpAvailable) {
        throw new PluginError("MCP unavailable, cannot recall", "E_MCP", false);
      }
    },

    "tool.execute.after": async (
      input: { name: string; args: Record<string, unknown>; resource?: string },
      output: { success?: boolean; error?: string }
    ) => {
      const duration = (output as any)?.duration || 0;
      const success = !output?.error;

      recordTrajectory(input.name, input.args, success, duration);

      if (!success) {
        const errorCode = getErrorCode(output.error || "");
        safeLog("error", `Tool ${input.name} failed: ${errorCode}`, {
          tool: input.name,
          error: output.error?.slice(0, 200),
        });
        if (errorCode === "E_MCP") {
          state.mcpAvailable = false;
        }
        return;
      }

      // Suggest tests for modified source files
      if (input.name === "edit" || input.name === "write") {
        const filePath = input.args?.filePath as string | undefined;
        if (filePath) {
          const testFile = suggestTestFile(filePath);
          if (testFile) {
            safeLog("info", `Source changed: ${filePath} → suggest test: ${testFile}`);
          }
        }
      }

      const learnTools = ["edit", "write", "bash"];
      if (learnTools.includes(input.name)) {
        try {
          await client?.tool("openflo_learn", {
            key: `tool:${input.name}:${Date.now()}`,
            content: `Executed ${input.name} in ${input.resource || ""}`,
            tags: ["tool", input.name],
          });
        } catch {
          state.mcpAvailable = false;
        }
      }
    },

    "session.initialize.after": async () => {
      state.initialized = true;
      try {
        await client?.tool("openflo_recall", { query: "__ping__" });
        state.mcpAvailable = true;
      } catch {
        state.mcpAvailable = false;
        safeLog("warn", "MCP not available at session start");
      }
    },

    "session.error": async (error: unknown) => {
      const code = getErrorCode(error);
      safeLog("error", `Session error: ${code}`, {
        message: error instanceof Error ? error.message : String(error),
      });
      try {
        await client?.tool("openflo_learn", {
          key: `error:${code}:${Date.now()}`,
          content: `Session error: ${error instanceof Error ? error.message : String(error)}`,
          tags: ["error", code],
        });
      } catch { }
    },
  };
}) satisfies Plugin;
