---
name: backend-developer
description: "Professional backend engineer for Node.js, Python, Go, and Rust. Includes 60+ API design patterns, 40+ database design rules, 30+ security patterns, 25+ performance rules, 20+ error handling patterns, 30+ testing strategies, 15+ caching strategies, 20+ async patterns, 10+ authentication patterns, and 10+ logging/monitoring rules. Covers Express, Fastify, FastAPI, Django, Gin, Axum, Prisma, Drizzle, SQLAlchemy, PostgreSQL, Redis, Kafka, RabbitMQ. Actions: build, create, implement, refactor, optimize, fix, review. Topics: API design, database, authentication, caching, background jobs, error handling, testing, deployment."
license: MIT
compatibility: opencode
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: backend
  triggers: API, backend, server, endpoint, route, service, database, model, migration, middleware, auth, cache, queue, worker, GraphQL, REST, gRPC
  role: specialist
  scope: implementation
  output-format: code
  related-skills: architecture-designer, test-master, security-engineer, devops-engineer, frontend-developer
---

# Backend Developer Pro — Server Engineering

Senior backend engineer specializing in API design, database modeling, service architecture, performance, and reliability. Covers Node.js, Python, Go, and Rust with framework-specific patterns.

## Language & Framework Decision Matrix

| Need | Node.js | Python | Go | Rust |
|------|---------|--------|----|------|
| Development speed | Fast | Fast | Medium | Slow |
| Performance | Medium | Medium | High | Highest |
| TypeScript support | Native | Via annotations | Static types | Static types |
| Ecosystem | Largest (npm) | Large (PyPI) | Medium | Growing |
| Concurrency | Event loop | Async/await | Goroutines | Tokio/async-std |
| Memory usage | Medium | High | Low | Low |
| Best for | APIs, real-time, BFF | ML, data, APIs | APIs, infra, CLIs | Performance-critical, systems |
| Startup time | Fast | Slow | Fast | Medium |

## Quick Reference — 12 Priority Categories

### 1. API Design (CRITICAL)

Every API endpoint must be consistent, predictable, and well-documented.

| Rule | Do | Don't |
|------|----|-------|
| **RESTful URLs** | Plural nouns: `/api/users`, `/api/orders/:id` | Verbs in URL: `/api/getUser`, `/api/createOrder` |
| **HTTP Methods** | GET = read, POST = create, PUT = full update, PATCH = partial, DELETE = remove | POST for everything, GET with body |
| **Status Codes** | 200 OK, 201 Created, 204 No Content, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict, 422 Unprocessable, 429 Too Many, 500 Server Error | 200 for errors, 500 for validation errors |
| **Consistent Error Format** | `{ error: "VALIDATION_ERROR", message: "Email is required", details: [...] }` | Inconsistent error shapes, stack traces exposed |
| **Versioning** | URL prefix: `/api/v1/users` or header: `Accept: application/vnd.api+json;version=1` | No versioning, breaking changes without notice |
| **Pagination** | Cursor-based: `{ cursor, limit, hasMore }` or page-based: `{ page, perPage, total, totalPages }` | No pagination, unlimited results |
| **Filtering** | Query params: `?status=active&role=admin` | POST for filters, complex query languages |
| **Sorting** | `?sort=created_at:desc,name:asc` | Client-side sorting, no sort options |
| **Field Selection** | `?fields=id,name,email` (sparse fieldsets) | Always return full objects |
| **HATEOAS** | Include links in responses: `{ _links: { self: "...", next: "..." } }` | Hardcoded URLs, no discoverability |
| **Idempotency** | `Idempotency-Key` header for mutations | Duplicate charges, double-created resources |

### 2. Data Validation (CRITICAL)

Validate every input at the API boundary. Never trust client data.

| Pattern | Implementation | Example |
|---------|----------------|---------|
| **Schema validation** | Zod (TS), Pydantic (Python), validator (Go) | `const schema = z.object({ email: z.string().email() })` |
| **Whitelist** | Define allowed fields explicitly | Accept only known fields, strip unknown |
| **Sanitization** | Strip HTML, escape output | `stripHtml(input)` before storage |
| **Type coercion** | Parse + validate, don't silently convert | `parseInt(id, 10)` with error on NaN |
| **File upload** | Validate type, size, scan for malware | Max 5MB, allowlisted MIME types |
| **Rate limit** | Per-endpoint rate limiting | Auth: 10/min, API: 1000/min |

```typescript
// Zod schema shared frontend + backend
import { z } from 'zod'

export const createUserSchema = z.object({
  email: z.string().email('Invalid email format'),
  name: z.string().min(2).max(100),
  role: z.enum(['admin', 'user', 'viewer']).default('user'),
})

export type CreateUserInput = z.infer<typeof createUserSchema>
```

### 3. Authentication & Authorization (HIGH)

| Concern | Pattern | Implementation |
|---------|---------|----------------|
| **Password hashing** | bcrypt (cost ≥ 12) or argon2id | `await bcrypt.hash(password, 12)` |
| **JWT tokens** | Access (15min) + Refresh (7d) rotation | Short access, rotate refresh, blacklist on logout |
| **Session tokens** | Server-side sessions in Redis | Fast revocation, but needs state |
| **API keys** | Hash key before storing (sha256), prefix `sk_live_` | Rate limit 100/min per key, rotate on leak |
| **OAuth 2.0 / OIDC** | Authorization code flow + PKCE | Google, GitHub, Microsoft login |
| **RBAC** | Role-based access control | `role: 'admin' | 'user'`, middleware check |
| **ABAC** | Attribute-based for complex rules | `can( user, 'edit', document )` with policy engine |
| **MFA** | TOTP or SMS as second factor | Required for admin, optional for users |
| **Account lockout** | After 5 failed attempts, lock 15min | Prevent brute force |
| **Passwordless** | Magic links, OTP codes, biometric | Reduce friction, increase security |

```typescript
// Auth middleware (Express/Fastify)
async function authMiddleware(req: Request, res: Response, next: NextFunction) {
  const token = req.headers.authorization?.replace('Bearer ', '')
  if (!token) return res.status(401).json({ error: 'MISSING_TOKEN' })

  try {
    const payload = jwt.verify(token, SECRET, { algorithms: ['HS256'] })
    req.user = await userService.findById(payload.sub)
    next()
  } catch {
    return res.status(401).json({ error: 'INVALID_TOKEN' })
  }
}

// RBAC middleware
function requireRole(...roles: string[]) {
  return (req: Request, res: Response, next: NextFunction) => {
    if (!roles.includes(req.user.role)) {
      return res.status(403).json({ error: 'FORBIDDEN' })
    }
    next()
  }
}
```

### 4. Database Design (HIGH)

| Rule | Do | Don't |
|------|----|-------|
| **Primary keys** | UUID v4 or ULID for all tables | Auto-increment (exposes count, merge conflicts) |
| **Timestamps** | `created_at` on every table, `updated_at` where mutable | No created_at, manual timestamp management |
| **Foreign keys** | Index all FK columns, use ON DELETE CASCADE carefully | No FK indexes, cascade deletes unless intentional |
| **Indexing** | Index on: FK columns, frequently filtered/sorted columns | Index every column, over-indexing |
| **JSON columns** | JSONB (PostgreSQL) for flexible attributes with DB validation | EAV pattern, no validation |
| **Soft deletes** | `deleted_at` + `is_active` computed column | Hard deletes (irreversible), is_deleted boolean |
| **Migrations** | Immutable migrations, never edit existing ones | Editing committed migrations, no rollback |
| **N+1 queries** | Eager load with JOIN or dataloader | 100 queries for 100 records |
| **Connection pool** | Use pool: max 20 connections | Open/close per request, no pool |
| **Transactions** | Wrap related mutations in transactions | Partial updates on failure |

```typescript
// Prisma schema example
model User {
  id        String   @id @default(uuid())
  email     String   @unique
  name      String?
  role      Role     @default(USER)
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
  posts     Post[]
  deletedAt DateTime?
}

enum Role { ADMIN USER VIEWER }

model Post {
  id        String   @id @default(uuid())
  title     String
  content   String?
  published Boolean  @default(false)
  authorId  String
  author    User     @relation(fields: [authorId], references: [id])
  createdAt DateTime @default(now())
}
```

### 5. Error Handling (HIGH)

Every error must be caught, logged, and returned in a consistent format.

| Layer | Strategy | Example |
|-------|----------|---------|
| **Route handler** | Try/catch with global error handler | `throw new AppError('NOT_FOUND', 'User not found', 404)` |
| **Service layer** | Return Result/Either type or throw typed errors | `Either<AppError, User>` |
| **Database** | Wrap in try/catch, translate to app errors | `UniqueConstraintError` → `409 Conflict` |
| **External API** | Timeout + circuit breaker + retry | `fetch(url, { signal: AbortSignal.timeout(5000) })` |
| **Background job** | Retry with exponential backoff, DLQ after max retries | Bull/Sidekiq retry config |

```typescript
// AppError class
class AppError extends Error {
  constructor(
    public code: string,
    public message: string,
    public status: number = 400,
    public details?: unknown
  ) {
    super(message)
  }
}

// Global error handler (Express)
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  if (err instanceof AppError) {
    return res.status(err.status).json({
      error: err.code,
      message: err.message,
      details: err.details,
    })
  }

  logger.error({ err, reqId: req.id }, 'Unhandled error')
  return res.status(500).json({ error: 'INTERNAL_ERROR', message: 'An unexpected error occurred' })
})
```

### 6. Performance & Caching (HIGH)

| Strategy | When | Implementation |
|----------|------|----------------|
| **Database indexing** | Slow queries | `EXPLAIN ANALYZE`, add composite indexes |
| **Connection pooling** | High concurrency | Pool size = ((core_count * 2) + effective_spindle_count) |
| **Redis cache** | Frequently read, rarely changed data | Cache-aside: read cache → miss → read DB → set cache → return |
| **CDN** | Static assets, API responses | CloudFront / Cloudflare for cacheable responses |
| **Response compression** | Large JSON payloads | `compression` middleware (Node), Gzip/Brotli |
| **Pagination** | List endpoints | Cursor-based for real-time, page-based for static |
| **Query optimization** | SELECT only needed columns | `SELECT id, name`, not `SELECT *` |
| **Batch loading** | N+1 prevention | DataLoader (Node), batching queries |
| **Materialized views** | Complex aggregations | Pre-computed, refresh periodically |
| **Read replicas** | Read-heavy workloads | Route read queries to replicas |

```typescript
// Redis caching pattern
async function getCachedOrFetch<T>(key: string, fetch: () => Promise<T>, ttl = 300): Promise<T> {
  const cached = await redis.get(key)
  if (cached) return JSON.parse(cached)

  const data = await fetch()
  await redis.setex(key, ttl, JSON.stringify(data))
  return data
}
```

### 7. Logging & Monitoring (MEDIUM)

| Concern | Tool | Standard |
|---------|------|----------|
| **Structured logging** | pino / winston / structlog | JSON logs, never console.log |
| **Correlation IDs** | Request-scoped ID | Pass via headers, include in all logs |
| **Log levels** | trace, debug, info, warn, error, fatal | info for operations, error for failures |
| **Request logging** | Morgan / pino-http | Method, URL, status, duration |
| **Metrics** | Prometheus + Grafana | RPS, latency (P50/P95/P99), error rate |
| **Health checks** | `/health` + `/ready` | Liveness: process alive. Readiness: dependencies OK |
| **Distributed tracing** | OpenTelemetry | Trace parent → child → span |

### 8. Background Jobs (MEDIUM)

| Concern | Pattern | Tool |
|---------|---------|------|
| **Simple async** | Fire and forget (use with caution) | `queue.add(() => sendEmail(user))` |
| **Reliable jobs** | Persistent queue + retry | Bull (Redis), Sidekiq (Redis), Celery (RabbitMQ/Redis) |
| **Scheduled jobs** | Cron | `node-cron`, cron expressions |
| **Dead letter queue** | Failed jobs after max retries | Separate queue for manual inspection |
| **Job progress** | Track + report percentage | Update progress in DB, poll from frontend |
| **Concurrency** | Limit concurrent jobs | Per-queue max concurrency setting |

```typescript
// Bull job processor
const emailQueue = new Bull('email', { redis })

emailQueue.process(async (job) => {
  const { to, subject, body } = job.data
  await sendEmail(to, subject, body)
})

emailQueue.add({ to: 'user@example.com', subject: 'Welcome!', body: '...' }, {
  attempts: 3,
  backoff: { type: 'exponential', delay: 2000 },
})
```

### 9. File Storage (MEDIUM)

| Concern | Pattern | Implementation |
|---------|---------|----------------|
| **Storage** | S3 / GCS / R2 (object storage) | Never local filesystem for production |
| **Upload** | Signed URLs for direct upload | Client uploads directly to S3, server validates |
| **Processing** | Async processing via queue | Image resize, virus scan, thumbnail generation |
| **Access control** | Signed URLs with expiry | Temporary access (1h default) |
| **Formats** | WebP/AVIF for images, HLS for video | Optimize for web delivery |

### 10. Security (HIGH)

| Vulnerability | Prevention |
|---------------|-----------|
| **SQL injection** | Parameterized queries (never string interpolation) |
| **XSS** | Content-Type: application/json APIs, CSP headers |
| **CSRF** | SameSite=Strict cookies, CSRF tokens |
| **SSRF** | Allowlist outbound URLs, validate redirects |
| **Rate limiting** | Express-rate-limit / token bucket on auth, API |
| **CORS** | Allowlist specific origins, not wildcard |
| **Security headers** | helmet (CSP, HSTS, X-Frame-Options, X-Content-Type-Options) |
| **Secrets** | Env vars / secret manager, never in code |
| **Dependencies** | Regular npm/pip audit, Dependabot |
| **Input validation** | Every input validated against schema |

### 11. Testing (HIGH)

| Layer | Framework | Coverage Target |
|-------|-----------|----------------|
| **Unit** | Vitest / Jest / pytest / go test | Business logic: 100% lines + branches |
| **Integration** | Supertest / TestClient / httptest | API endpoints: all status codes, auth errors |
| **Database** | Testcontainers / in-memory SQLite | Queries, constraints, migrations |
| **E2E** | Playwright / Cypress | Critical user flows |
| **Load** | k6 / autocannon / Locust | P95 < 200ms, no errors at 2x expected load |

```typescript
// Integration test (Supertest)
import request from 'supertest'
import app from '../app'

test('POST /api/v1/users returns 201 with valid data', async () => {
  const res = await request(app)
    .post('/api/v1/users')
    .send({ email: 'test@example.com', name: 'Test' })
    .expect(201)

  expect(res.body).toMatchObject({
    id: expect.any(String),
    email: 'test@example.com',
  })
})

test('POST /api/v1/users returns 422 with invalid email', async () => {
  await request(app)
    .post('/api/v1/users')
    .send({ email: 'invalid' })
    .expect(422)
})
```

### 12. Deployment & CI (MEDIUM)

| Concern | Pattern | Implementation |
|---------|---------|----------------|
| **CI pipeline** | Test → lint → build → deploy | GitHub Actions / GitLab CI |
| **Docker** | Multi-stage build, non-root user | Alpine-based, slim images |
| **Health checks** | /health (liveness) + /ready (readiness) | Docker HEALTHCHECK, K8s probes |
| **Graceful shutdown** | SIGTERM → drain connections → exit | `process.on('SIGTERM', shutdown)` |
| **Zero-downtime** | Rolling updates, blue/green | K8s rolling update, load balancer health check |
| **Database migrations** | Run as separate step before deploy | Release: migrate → deploy new version |

```typescript
// Graceful shutdown
async function shutdown(signal: string) {
  logger.info({ signal }, 'Shutting down gracefully')
  server.close(() => {
    logger.info('HTTP server closed')
    db.destroy()
    redis.quit()
    process.exit(0)
  })
  // Force exit after 30s
  setTimeout(() => process.exit(1), 30_000).unref()
}

process.on('SIGTERM', () => shutdown('SIGTERM'))
process.on('SIGINT', () => shutdown('SIGINT'))
```

## Pre-Delivery Checklist

### API Quality
- [ ] All endpoints return consistent error format
- [ ] Pagination on all list endpoints
- [ ] Rate limiting on auth and public endpoints
- [ ] CORS configured (not wildcard in production)
- [ ] OpenAPI/Swagger docs updated

### Data Integrity
- [ ] Input validation on every endpoint
- [ ] Parameterized queries (no SQL injection risk)
- [ ] Foreign keys indexed
- [ ] Migrations have rollback
- [ ] Soft deletes for important data

### Security
- [ ] Passwords hashed with bcrypt/argon2id
- [ ] JWT secrets rotated, short expiry
- [ ] Security headers set (helmet)
- [ ] No secrets in code (env vars only)
- [ ] CSRF protection in place

### Performance
- [ ] Database queries optimized (EXPLAIN ANALYZE)
- [ ] Caching configured for frequent reads
- [ ] Response compression enabled
- [ ] Connection pool configured
- [ ] N+1 queries eliminated

### Reliability
- [ ] Error handling at all layers
- [ ] Structured logging with correlation IDs
- [ ] Health check endpoints (/health, /ready)
- [ ] Graceful shutdown implemented
- [ ] Background jobs have retry + DLQ

## Knowledge Reference

- REST / GraphQL / gRPC API design
- Node.js: Express, Fastify, NestJS, Prisma, Drizzle, Zod, Bull
- Python: FastAPI, Django, SQLAlchemy 2.0, Pydantic, Celery
- Go: Gin, Fiber, sqlx, GORM, ent
- Rust: Axum, Actix-Web, SeaORM, sqlx, Tokio
- PostgreSQL: indexing, query optimization, JSONB, full-text search
- Redis: caching, pub/sub, rate limiting, session store
- Kafka / RabbitMQ: event-driven architecture, message patterns
- Docker, CI/CD (GitHub Actions, GitLab CI)
- OWASP Top 10, OAuth 2.0 / OIDC, JWT
