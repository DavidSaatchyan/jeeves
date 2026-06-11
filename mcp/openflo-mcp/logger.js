import { appendFileSync, mkdirSync, existsSync, statSync, readdirSync, unlinkSync, renameSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOG_DIR = join(__dirname, "..", "..", "..", ".openflo-data", "logs");

if (!existsSync(LOG_DIR)) mkdirSync(LOG_DIR, { recursive: true });

const LEVELS = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 };
const DEFAULT_LEVEL = "INFO";
const MAX_LOG_SIZE = 10 * 1024 * 1024; // 10MB per file
const MAX_LOG_FILES = 3;

function getLogFile() {
  const date = new Date().toISOString().slice(0, 10);
  return join(LOG_DIR, `openflo-${date}.jsonl`);
}

function trimLogs() {
  try {
    const files = readdirSync(LOG_DIR).filter(f => f.endsWith(".jsonl")).sort().reverse();
    while (files.length > MAX_LOG_FILES) {
      const oldest = files.pop();
      unlinkSync(join(LOG_DIR, oldest));
    }
  } catch {}
}

function rotateIfNeeded(filePath) {
  try {
    if (existsSync(filePath) && statSync(filePath).size > MAX_LOG_SIZE) {
      const rotated = filePath + ".1";
      if (existsSync(rotated)) unlinkSync(rotated);
      renameSync(filePath, rotated);
      trimLogs();
    }
  } catch {}
}

export class Logger {
  constructor(component, options = {}) {
    this.component = component;
    this.minLevel = LEVELS[options.level || DEFAULT_LEVEL] || LEVELS.INFO;
    this.toStdErr = options.stderr !== false;
  }

  _log(level, message, metadata) {
    if (LEVELS[level] < this.minLevel) return;

    const entry = {
      timestamp: new Date().toISOString(),
      level,
      component: this.component,
      message,
      metadata: metadata || {},
    };

    const line = JSON.stringify(entry) + "\n";

    if (this.toStdErr) {
      process.stderr.write(line);
    }

    try {
      const filePath = getLogFile();
      rotateIfNeeded(filePath);
      appendFileSync(filePath, line);
    } catch {}
  }

  debug(message, metadata) { this._log("DEBUG", message, metadata); }
  info(message, metadata) { this._log("INFO", message, metadata); }
  warn(message, metadata) { this._log("WARN", message, metadata); }
  error(message, metadata) { this._log("ERROR", message, metadata); }

  toolCall(toolName, args, durationMs) {
    this.info("Tool call", { tool: toolName, duration: durationMs, args: this._sanitize(args) });
  }

  _sanitize(obj) {
    if (!obj || typeof obj !== "object") return obj;
    const sanitized = { ...obj };
    if (sanitized.content) sanitized.content = sanitized.content.slice(0, 200);
    if (sanitized.text) sanitized.text = sanitized.text.slice(0, 200);
    return sanitized;
  }

  static getLogFiles() {
    try {
      return readdirSync(LOG_DIR).filter(f => f.endsWith(".jsonl")).sort();
    } catch { return []; }
  }

  static readLogs(options = {}) {
    const { component, level, limit = 100, since } = options;
    const { readFileSync } = require("fs");
    const results = [];

    try {
      const files = readdirSync(LOG_DIR).filter(f => f.endsWith(".jsonl")).sort().reverse();
      for (const file of files) {
        if (results.length >= limit) break;
        const lines = readFileSync(join(LOG_DIR, file), "utf-8").split("\n").filter(Boolean);
        for (const line of lines.reverse()) {
          if (results.length >= limit) break;
          try {
            const entry = JSON.parse(line);
            if (component && entry.component !== component) continue;
            if (level && LEVELS[entry.level] < LEVELS[level]) continue;
            if (since && new Date(entry.timestamp) < new Date(since)) continue;
            results.push(entry);
          } catch {}
        }
      }
    } catch {}
    return results;
  }
}
