import http from "node:http";
import { getStats, listTags, load } from "./store.js";
import { getAllGoals } from "./goals.js";
import { Logger } from "./logger.js";

export function startHttpServer(port = 4321) {
  const server = http.createServer((req, res) => {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    if (req.method === "OPTIONS") {
      res.writeHead(204, corsHeaders);
      res.end();
      return;
    }

    if (req.method !== "GET") {
      res.writeHead(405, corsHeaders);
      res.end(JSON.stringify({ error: "Method not allowed" }));
      return;
    }

    try {
      const url = new URL(req.url, `http://localhost:${port}`);

      if (url.pathname === "/health") {
        res.writeHead(200, { "Content-Type": "application/json", ...corsHeaders });
        res.end(JSON.stringify({ status: "ok", uptime: process.uptime() }));
        return;
      }

      if (url.pathname === "/v1/stats") {
        res.writeHead(200, { "Content-Type": "application/json", ...corsHeaders });
        res.end(JSON.stringify(getStats()));
        return;
      }

      if (url.pathname === "/v1/tags") {
        res.writeHead(200, { "Content-Type": "application/json", ...corsHeaders });
        res.end(JSON.stringify(listTags()));
        return;
      }

      if (url.pathname === "/v1/memories") {
        const memories = load();
        const limit = Math.min(parseInt(url.searchParams.get("limit") || "50"), 200);
        const tag = url.searchParams.get("tag");
        let results = memories;
        if (tag) results = memories.filter(m => m.tags.includes(tag.toLowerCase()));
        res.writeHead(200, { "Content-Type": "application/json", ...corsHeaders });
        res.end(JSON.stringify(results.slice(0, limit)));
        return;
      }

      if (url.pathname === "/v1/logs") {
        const level = url.searchParams.get("level") || undefined;
        const component = url.searchParams.get("component") || undefined;
        const limit = parseInt(url.searchParams.get("limit") || "50", 10);
        res.writeHead(200, { "Content-Type": "application/json", ...corsHeaders });
        res.end(JSON.stringify(Logger.readLogs({ level, component, limit })));
        return;
      }

      if (url.pathname === "/v1/agents") {
        res.writeHead(200, { "Content-Type": "application/json", ...corsHeaders });
        res.end(JSON.stringify({ uptime: process.uptime(), goals: getAllGoals().length }));
        return;
      }

      res.writeHead(404, corsHeaders);
      res.end(JSON.stringify({ error: "Not found", paths: ["/health", "/v1/stats", "/v1/tags", "/v1/memories", "/v1/logs", "/v1/agents"] }));
    } catch (e) {
      res.writeHead(500, corsHeaders);
      res.end(JSON.stringify({ error: e.message }));
    }
  });

  server.listen(port, "127.0.0.1", () => {
    process.stderr.write(`[openflo-mcp] HTTP server on http://127.0.0.1:${port}\n`);
  });

  server.on("error", (err) => {
    if (err.code === "EADDRINUSE") {
      process.stderr.write(`[openflo-mcp] Port ${port} in use, HTTP disabled\n`);
    } else {
      process.stderr.write(`[openflo-mcp] HTTP error: ${err.message}\n`);
    }
  });

  return server;
}
