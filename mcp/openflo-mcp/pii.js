const PATTERNS = [
  { type: "email", severity: "medium", pattern: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g },
  { type: "aws-key", severity: "high", pattern: /(?:AKIA|ASIA)[A-Z0-9]{16}/g },
  { type: "github-token", severity: "high", pattern: /ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}|ghu_[a-zA-Z0-9]{36}|ghs_[a-zA-Z0-9]{36}|ghr_[a-zA-Z0-9]{36}/g },
  { type: "ssh-key", severity: "high", pattern: /-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----/g },
  { type: "phone", severity: "medium", pattern: /(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,9}/g },
  { type: "credit-card", severity: "high", pattern: /\b(?:\d{4}[-\s]?){3}\d{4}\b/g },
  { type: "ip-address", severity: "low", pattern: /\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b/g },
  { type: "slack-token", severity: "high", pattern: /xox[baprs]-[a-zA-Z0-9]{10,}/g },
  { type: "jwt", severity: "medium", pattern: /eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}/g },
  { type: "pgp-key", severity: "high", pattern: /-----BEGIN PGP (?:PUBLIC |PRIVATE )?KEY BLOCK-----[\s\S]*?-----END PGP (?:PUBLIC |PRIVATE )?KEY BLOCK-----/g },
];

const CONFIDENCE_MAP = {
  "aws-key": 0.95,
  "github-token": 0.95,
  "ssh-key": 0.95,
  "pgp-key": 0.95,
  "slack-token": 0.9,
  "credit-card": 0.9,
  "email": 0.8,
  "jwt": 0.7,
  "phone": 0.5,
  "ip-address": 0.3,
};

export function scanPII(text, options = {}) {
  const { mode = "warn" } = options; // warn | block | redact | pass
  const findings = [];
  let redacted = text;

  for (const { type, severity, pattern } of PATTERNS) {
    let match;
    pattern.lastIndex = 0;
    while ((match = pattern.exec(text)) !== null) {
      const confidence = CONFIDENCE_MAP[type] || 0.5;
      findings.push({
        type,
        severity,
        confidence,
        match: match[0].slice(0, 80),
        index: match.index,
        length: match[0].length,
      });

      if (mode === "redact") {
        const stars = "*".repeat(match[0].length);
        redacted = redacted.slice(0, match.index) + stars + redacted.slice(match.index + match[0].length);
        pattern.lastIndex = match.index + stars.length;
      }
    }
  }

  findings.sort((a, b) => b.confidence - a.confidence);

  const highConfidence = findings.filter((f) => f.confidence >= 0.9);

  return {
    findings,
    count: findings.length,
    highConfidence: highConfidence.length,
    blocked: mode === "block" && highConfidence.length > 0,
    redacted: mode === "redact" ? redacted : undefined,
    summary: findings.length > 0
      ? findings.map((f) => `${f.type}(${f.severity}, ${Math.round(f.confidence * 100)}%)`).join(", ")
      : "No PII detected",
  };
}

export function getToolDefinition() {
  return {
    name: "openflo_pii_scan",
    description: "Scan text for PII (emails, keys, tokens, credit cards, etc.)",
    inputSchema: {
      type: "object",
      properties: {
        text: { type: "string", description: "Text to scan for PII" },
        mode: {
          type: "string",
          enum: ["warn", "block", "redact", "pass"],
          description: "Action mode: warn (default), block (error on high confidence), redact (replace with ***), pass (find only)",
          default: "warn",
        },
      },
      required: ["text"],
    },
  };
}

export function handlePIIScan(args) {
  const text = String(args.text || "");
  if (!text) {
    return { content: [{ type: "text", text: "No text provided to scan." }] };
  }

  const result = scanPII(text, { mode: args.mode || "warn" });

  if (result.blocked) {
    throw new (class extends Error {
      constructor() {
        super(`PII scan blocked: ${result.highConfidence} high-confidence findings`);
        this.code = -32099;
        this.name = "PIIBlockedError";
      }
    })();
  }

  const lines = [
    `PII Scan Results:`,
    `  Total findings: ${result.count}`,
    `  High confidence: ${result.highConfidence}`,
    `  Summary: ${result.summary}`,
  ];

  if (result.findings.length > 0) {
    lines.push(`\nDetails:`);
    for (const f of result.findings.slice(0, 20)) {
      lines.push(`  [${f.type}] ${f.match} (${f.severity}, ${Math.round(f.confidence * 100)}% conf)`);
    }
    if (result.findings.length > 20) {
      lines.push(`  ... and ${result.findings.length - 20} more`);
    }
  }

  if (result.redacted) {
    lines.push(`\nRedacted Text:\n${result.redacted}`);
  }

  return { content: [{ type: "text", text: lines.join("\n") }] };
}
