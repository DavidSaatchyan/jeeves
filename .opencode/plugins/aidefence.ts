import type { Plugin } from "@opencode-ai/plugin";

type Mode = "block" | "warn" | "off";

const DEFAULT_PATTERNS = [
  { pattern: /ignore\s+(all\s+)?previous/i, severity: "high", label: "ignore-previous" },
  { pattern: /you\s+are\s+(now\s+)?a/i, severity: "high", label: "role-change" },
  { pattern: /system\s*:\s*/i, severity: "high", label: "system-override" },
  { pattern: /[A-Za-z0-9+/]{40,}={0,2}/, severity: "medium", label: "base64-candidate" },
  { pattern: /[\u200B\u200C\u200D\uFEFF\u200E\u200F]/, severity: "medium", label: "zero-width-char" },
  { pattern: /print\(.*\)|eval\(.*\)|exec\(.*\)|process\.env/i, severity: "medium", label: "code-exec" },
  { pattern: /password|secret|api[_-]?key|token/i, severity: "low", label: "sensitive-ref" },
  { pattern: /<script\b[^>]*>[\s\S]*?<\/script>/i, severity: "high", label: "xss" },
  { pattern: /(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?):\d{4,5}/i, severity: "low", label: "ip-port" },
];

export default (async ({ client }) => {
  const mode: Mode = (client?.config as any)?.aidefence?.mode || "warn";
  const customPatterns: Array<{ pattern: string; severity: string; label: string }> =
    (client?.config as any)?.aidefence?.patterns || [];
  const allPatterns = [
    ...DEFAULT_PATTERNS,
    ...customPatterns.map((p) => ({
      pattern: new RegExp(p.pattern, "i"),
      severity: p.severity,
      label: p.label,
    })),
  ];

  function scan(text: string) {
    const findings: Array<{ label: string; severity: string; match: string }> = [];
    for (const { pattern, severity, label } of allPatterns) {
      const match = text.match(pattern);
      if (match) {
        findings.push({ label, severity, match: match[0].slice(0, 80) });
        if (severity === "high" && mode === "block") break;
      }
    }
    return findings;
  }

  return {
    "config": (config: Record<string, unknown>) => {
      if (!config.plugins) config.plugins = [];
      if (!config.plugins.includes("aidefence")) {
        console.log(`[aidefence] Active (mode: ${mode}, patterns: ${allPatterns.length})`);
      }
    },

    "tool.execute.before": async (input: { name: string; args: Record<string, unknown> }) => {
      if (mode === "off") return;
      if (input.name !== "read" && input.name !== "edit" && input.name !== "write") return;

      const textToScan = [
        input.args?.content,
        input.args?.oldString,
        input.args?.newString,
        ...(Array.isArray(input.args?.filePath) ? input.args.filePath : [input.args?.filePath]),
      ]
        .filter(Boolean)
        .join(" ");

      if (!textToScan) return;

      const findings = scan(textToScan);
      if (findings.length === 0) return;

      if (mode === "block") {
        const highSeverity = findings.filter((f) => f.severity === "high");
        if (highSeverity.length > 0) {
          throw new Error(
            `[aidefence] BLOCKED: ${highSeverity.map((f) => f.label).join(", ")} ` +
              `in ${input.name}. Match: "${highSeverity[0].match.slice(0, 60)}..."`
          );
        }
      }

      if (mode === "warn") {
        console.log(
          `[aidefence] WARN: ${findings.map((f) => `${f.label}(${f.severity})`).join(", ")} in ${input.name}`
        );
      }
    },

    "tool.execute.after": async (
      input: { name: string; args: Record<string, unknown> },
      output: { success?: boolean; error?: string; content?: string }
    ) => {
      if (mode === "off") return;
      if (input.name !== "read") return;
      if (!output?.success) return;

      const content = output?.content || "";
      if (!content || content.length < 100) return;

      // Sample: scan first 10k chars and last 5k chars for injection patterns
      const head = content.slice(0, 10000);
      const tail = content.slice(-5000);

      const findings = scan(head + "\n" + tail);
      if (findings.length === 0) return;

      const path = input.args?.filePath || "unknown";
      if (mode === "block") {
        const highSeverity = findings.filter((f) => f.severity === "high");
        if (highSeverity.length > 0) {
          console.log(
            `[aidefence] BLOCKED in file ${path}: ${highSeverity.map((f) => f.label).join(", ")}`
          );
        }
      } else {
        console.log(
          `[aidefence] WARN in file ${path}: ${findings.map((f) => `${f.label}(${f.severity})`).join(", ")}`
        );
      }
    },
  };
}) satisfies Plugin;
