const counters = {};
const latencies = {};
const startTime = Date.now();

export function increment(counter, value = 1) {
  counters[counter] = (counters[counter] || 0) + value;
}

export function recordLatency(operation, durationMs) {
  if (!latencies[operation]) {
    latencies[operation] = { count: 0, total: 0, min: Infinity, max: 0 };
  }
  const l = latencies[operation];
  l.count++;
  l.total += durationMs;
  if (durationMs < l.min) l.min = durationMs;
  if (durationMs > l.max) l.max = durationMs;
}

export function getMetrics() {
  const uptime = Math.floor((Date.now() - startTime) / 1000);

  const latencySummary = {};
  for (const [op, l] of Object.entries(latencies)) {
    latencySummary[op] = {
      count: l.count,
      avg: Math.round(l.total / l.count),
      min: l.min,
      max: l.max,
    };
  }

  return {
    uptime,
    uptimeHuman: `${Math.floor(uptime / 60)}m ${uptime % 60}s`,
    counters: { ...counters },
    latencies: latencySummary,
    toolCallCount: counters["tool.call"] || 0,
    errorCount: counters["error"] || 0,
    memoryCount: counters["memory.created"] || 0,
  };
}

export function getToolDefinition() {
  return {
    name: "openflo_metrics",
    description: "Get internal server metrics (uptime, counters, latencies)",
    inputSchema: {
      type: "object",
      properties: {},
    },
  };
}

export function handleMetrics(args) {
  const m = getMetrics();
  const lines = [
    `OpenFlo MCP Metrics`,
    `  Uptime: ${m.uptimeHuman}`,
    `  Tool calls: ${m.toolCallCount}`,
    `  Errors: ${m.errorCount}`,
    `  Memories created: ${m.memoryCount}`,
    `\nCounters:`,
    ...Object.entries(m.counters).map(([k, v]) => `  ${k}: ${v}`),
  ];

  if (Object.keys(m.latencies).length > 0) {
    lines.push(`\nLatencies (ms):`);
    for (const [op, l] of Object.entries(m.latencies)) {
      lines.push(`  ${op}: avg=${l.avg} min=${l.min} max=${l.max} count=${l.count}`);
    }
  }

  return { content: [{ type: "text", text: lines.join("\n") }] };
}
