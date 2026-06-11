---
name: workers
description: "Multi-agent parallel execution engine for batch operations. Distributes independent tasks across worker agents with progress tracking, result aggregation, and error isolation. Supports parallel file processing, batch testing, bulk migrations, and concurrent code reviews."
license: MIT
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: execution
  triggers: parallel, batch, concurrent, worker, distribute, bulk, mass, multi-file
  scope: execution
---

# Workers — Parallel Execution Engine

Distributes independent tasks across worker agents for parallel execution. Manages queue, progress, and result aggregation.

## When to Use Workers

| Task Type | Example | Worker Count |
|-----------|---------|--------------|
| **Batch file processing** | Lint 50 files | 5 parallel workers |
| **Parallel testing** | Run 20 test suites | 4 parallel workers |
| **Bulk migration** | Migrate 10 services | 3 parallel workers |
| **Concurrent review** | Review 15 PR files | 5 parallel reviewers |
| **Data transformation** | Process 1000 records | 10 parallel workers |

## Worker Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `maxConcurrent` | 3 | Max parallel workers |
| `timeout` | 120000 | Per-worker timeout (ms) |
| `retryCount` | 1 | Retries on failure |
| `batchSize` | 10 | Items per worker batch |

## Pattern

1. **Split** — Divide task into N independent units
2. **Distribute** — Assign to workers (max concurrent limit)
3. **Execute** — Workers run in parallel
4. **Collect** — Aggregate results
5. **Report** — Summary: passed, failed, errors

```
                    ┌─ Worker 1 (files 1-10) ─ Success ─┐
Input (50 files) ───┼─ Worker 2 (files 11-20) ─ Error ─┼─ Aggregate → Report
                    └─ Worker 3 (files 21-30) ─ Success ─┘
                    ...
```

## Failure Handling

| Failure Type | Action | Impact |
|-------------|--------|--------|
| Worker timeout | Retry once, then skip | Affects only that batch |
| Worker error | Log error, continue | Other workers unaffected |
| Partial results | Return what succeeded | Report partial success |
| All workers fail | Fail entire batch | Return all errors |

## Best Practices

| Do | Don't |
|----|-------|
| Split work into truly independent units | Create dependencies between workers |
| Set appropriate timeouts per task type | Use default timeout for everything |
| Handle partial results gracefully | Require all-or-nothing |
| Log worker progress per batch | Log every item individually |
