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
      CREATE TABLE IF NOT EXISTS goals (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        description TEXT NOT NULL,
        plan_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS goal_tasks (
        id TEXT PRIMARY KEY,
        goal_id TEXT NOT NULL REFERENCES goals(id),
        label TEXT NOT NULL,
        priority TEXT NOT NULL DEFAULT 'P2',
        estimated_hours REAL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'pending',
        depends_on TEXT DEFAULT '[]',
        blocks TEXT DEFAULT '[]',
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_goal_tasks_goal ON goal_tasks(goal_id);
    `);
    return db;
  } catch { return null; }
}

export function saveGoal(name, description, planJson) {
  const d = getDb();
  if (!d) return null;

  const id = require("crypto").randomUUID();
  d.prepare(`
    INSERT INTO goals (id, name, description, plan_json)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(name) DO UPDATE SET
      description = excluded.description,
      plan_json = excluded.plan_json,
      updated_at = datetime('now')
  `).run(id, name, description, JSON.stringify(planJson));

  return { id, name };
}

export function loadGoal(name) {
  const d = getDb();
  if (!d) return null;
  const goal = d.prepare("SELECT * FROM goals WHERE name = ?").get(name);
  if (!goal) return null;
  const tasks = d.prepare("SELECT * FROM goal_tasks WHERE goal_id = ? ORDER BY priority, created_at").all(goal.id);
  return {
    id: goal.id,
    name: goal.name,
    description: goal.description,
    plan: JSON.parse(goal.plan_json || "{}"),
    status: goal.status,
    tasks: tasks.map(t => ({
      ...t,
      depends_on: JSON.parse(t.depends_on || "[]"),
      blocks: JSON.parse(t.blocks || "[]"),
    })),
    createdAt: goal.created_at,
    updatedAt: goal.updated_at,
  };
}

export function addTask(goalId, label, options = {}) {
  const d = getDb();
  if (!d) return null;
  const id = require("crypto").randomUUID();
  d.prepare(`
    INSERT INTO goal_tasks (id, goal_id, label, priority, estimated_hours, depends_on, blocks, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    id, goalId, label,
    options.priority || "P2",
    options.estimatedHours || 1,
    JSON.stringify(options.dependsOn || []),
    JSON.stringify(options.blocks || []),
    options.notes || null
  );
  return { id, label };
}

export function updateTaskStatus(taskId, status) {
  const d = getDb();
  if (!d) return;
  d.prepare("UPDATE goal_tasks SET status = ? WHERE id = ?").run(status, taskId);
}

export function getGoalStatus(goalId) {
  const d = getDb();
  if (!d) return {};
  const tasks = d.prepare("SELECT * FROM goal_tasks WHERE goal_id = ?").all(goalId);
  const total = tasks.length;
  const completed = tasks.filter(t => t.status === "completed").length;
  const blocked = tasks.filter(t => t.status === "blocked").length;
  const inProgress = tasks.filter(t => t.status === "in_progress").length;
  const pending = tasks.filter(t => t.status === "pending").length;
  const totalHours = tasks.reduce((s, t) => s + (t.estimated_hours || 0), 0);
  const doneHours = tasks.filter(t => t.status === "completed").reduce((s, t) => s + (t.estimated_hours || 0), 0);

  // Find what's blocking what
  const blockers = [];
  for (const t of tasks) {
    if (t.status === "blocked") {
      blockers.push({ task: t.label, depends: JSON.parse(t.depends_on || "[]") });
    }
  }

  return {
    total, completed, blocked, inProgress, pending,
    progressPercent: total > 0 ? Math.round((completed / total) * 100) : 0,
    hoursRemaining: totalHours - doneHours,
    blockers,
    nextSuggested: tasks.filter(t => t.status === "pending").slice(0, 3).map(t => t.label),
  };
}

// T8.3: Adaptive Replanning
export function adaptiveReplan(goalId) {
  const d = getDb();
  if (!d) return null;

  const tasks = d.prepare("SELECT * FROM goal_tasks WHERE goal_id = ? ORDER BY priority, created_at").all(goalId);
  const status = getGoalStatus(goalId);

  if (status.blockers.length === 0 && status.progressPercent >= 0) {
    return { action: "none", reason: "No blockers found, plan is on track" };
  }

  // Find blocked tasks and suggest alternatives
  const suggestions = [];
  const blockedTasks = tasks.filter(t => t.status === "blocked");
  const pendingTasks = tasks.filter(t => t.status === "pending");
  const completedTasks = tasks.filter(t => t.status === "completed");

  for (const bt of blockedTasks) {
    const deps = JSON.parse(bt.depends_on || "[]");
    const unresolvedDeps = deps.filter(d => !tasks.find(t => t.label === d && t.status === "completed"));

    // Suggest parallel work: unblocked pending tasks that don't depend on blockers
    const parallelCandidates = pendingTasks.filter(pt => {
      const ptDeps = JSON.parse(pt.depends_on || "[]");
      return !ptDeps.some(d => unresolvedDeps.includes(d));
    });

    if (parallelCandidates.length > 0) {
      suggestions.push({
        type: "parallel",
        blocked: bt.label,
        blockedBy: unresolvedDeps,
        suggestion: `Work on "${parallelCandidates[0].label}" while unblocking "${bt.label}"`,
        candidates: parallelCandidates.slice(0, 3).map(t => t.label),
      });
    }

    // Suggest dependency reprioritization
    if (unresolvedDeps.length > 0) {
      suggestions.push({
        type: "reprioritize",
        blocked: bt.label,
        blockedBy: unresolvedDeps,
        suggestion: `Prioritize completing: ${unresolvedDeps.join(", ")}`,
      });
    }
  }

  return {
    action: suggestions.length > 0 ? "suggestions" : "none",
    goalStatus: {
      completed: status.completed,
      inProgress: status.inProgress,
      blocked: status.blocked,
      pending: status.pending,
      progressPercent: status.progressPercent,
    },
    suggestions,
  };
}

export function getAllGoals() {
  const d = getDb();
  if (!d) return [];
  return d.prepare("SELECT id, name, description, status, created_at FROM goals ORDER BY created_at DESC").all();
}

export function getToolDefinitions() {
  return [
    {
      name: "openflo_goal_save",
      description: "Save a goal plan with sub-tasks",
      inputSchema: {
        type: "object",
        properties: {
          name: { type: "string", description: "Goal name (unique)" },
          description: { type: "string", description: "Goal description" },
          plan: {
            type: "object",
            description: "Plan JSON with tasks array (label, priority, estimatedHours, dependsOn, blocks)",
          },
        },
        required: ["name", "description", "plan"],
      },
    },
    {
      name: "openflo_goal_load",
      description: "Load a saved goal plan with tasks and status",
      inputSchema: {
        type: "object",
        properties: {
          name: { type: "string", description: "Goal name" },
        },
        required: ["name"],
      },
    },
    {
      name: "openflo_goal_status",
      description: "Get current goal progress and blocking issues",
      inputSchema: {
        type: "object",
        properties: {
          name: { type: "string", description: "Goal name (omit for all goals)" },
        },
      },
    },
    {
      name: "openflo_goal_replan",
      description: "Analyze a goal for blockers and suggest adaptive replanning",
      inputSchema: {
        type: "object",
        properties: {
          name: { type: "string", description: "Goal name to analyze" },
        },
        required: ["name"],
      },
    },
  ];
}

export function handleGoalTool(name, args) {
  switch (name) {
    case "openflo_goal_save": {
      if (!args?.name || !args?.description) throw mcpError(-32602, "name and description are required");
      const result = saveGoal(args.name, args.description, args.plan || {});
      if (args.plan?.tasks) {
        for (const task of args.plan.tasks) {
          addTask(result.id, task.label, task);
        }
      }
      return { content: [{ type: "text", text: `Goal "${args.name}" saved.` }] };
    }

    case "openflo_goal_load": {
      const goal = loadGoal(args.name);
      if (!goal) return { content: [{ type: "text", text: `Goal "${args.name}" not found.` }] };

      const lines = [
        `Goal: ${goal.name}`,
        `  ${goal.description}`,
        `  Status: ${goal.status}`,
        `  Created: ${goal.createdAt}`,
        `\nTasks (${goal.tasks.length}):`,
      ];

      for (const t of goal.tasks) {
        const deps = t.depends_on.length > 0 ? ` [depends: ${t.depends_on.join(", ")}]` : "";
        const blocks = t.blocks.length > 0 ? ` [blocks: ${t.blocks.join(", ")}]` : "";
        lines.push(`  [${t.priority}] ${t.label} — ${t.status} (${t.estimated_hours}h)${deps}${blocks}`);
      }

      return { content: [{ type: "text", text: lines.join("\n") }] };
    }

    case "openflo_goal_status": {
      if (args?.name) {
        const goal = loadGoal(args.name);
        if (!goal) return { content: [{ type: "text", text: `Goal "${args.name}" not found.` }] };
        const status = getGoalStatus(goal.id);
        const lines = [
          `Goal: ${goal.name}`,
          `  Progress: ${status.progressPercent}% (${status.completed}/${status.total})`,
          `  Hours remaining: ${status.hoursRemaining}h`,
          `  Blocked: ${status.blocked} | In Progress: ${status.inProgress} | Pending: ${status.pending}`,
        ];
        if (status.blockers.length > 0) {
          lines.push(`  Blockers:`);
          for (const b of status.blockers) {
            lines.push(`    - ${b.task} waiting on: ${b.depends.join(", ")}`);
          }
        }
        if (status.nextSuggested.length > 0) {
          lines.push(`\n  Suggested next: ${status.nextSuggested.join(", ")}`);
        }
        return { content: [{ type: "text", text: lines.join("\n") }] };
      }

      const all = getAllGoals();
      if (all.length === 0) return { content: [{ type: "text", text: "No goals found." }] };

      const lines = ["All Goals:"];
      for (const g of all) {
        const s = getGoalStatus(g.id);
        lines.push(`  ${g.name}: ${s.progressPercent}% (${s.completed}/${s.total}) — ${g.status}`);
      }
      return { content: [{ type: "text", text: lines.join("\n") }] };
    }

    case "openflo_goal_replan": {
      const goal = loadGoal(args.name);
      if (!goal) return { content: [{ type: "text", text: `Goal "${args.name}" not found.` }] };
      const result = adaptiveReplan(goal.id);
      if (!result || result.action === "none") {
        return { content: [{ type: "text", text: `Goal "${args.name}": ${result?.reason || "no issues found."}` }] };
      }
      const lines = [
        `Adaptive Replan for "${args.name}":`,
        `  Progress: ${result.goalStatus.progressPercent}% (${result.goalStatus.completed}/${result.goalStatus.completed + result.goalStatus.inProgress + result.goalStatus.blocked + result.goalStatus.pending})`,
        `  Blocked: ${result.goalStatus.blocked} | In Progress: ${result.goalStatus.inProgress} | Pending: ${result.goalStatus.pending}`,
        ``,
        `Suggestions:`,
      ];
      for (const s of result.suggestions) {
        lines.push(`  [${s.type}] ${s.suggestion}`);
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
