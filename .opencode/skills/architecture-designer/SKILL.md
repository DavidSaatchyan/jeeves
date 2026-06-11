---
name: architecture-designer
description: "Professional system architect for distributed systems, microservices, and enterprise architecture. Includes 30+ architectural patterns, 25+ design patterns, 20+ data patterns (CQRS, Event Sourcing, Saga), 15+ integration patterns, 25+ scalability patterns, 20+ reliability patterns, 15+ security architecture patterns, 10+ deployment patterns, 20+ ADR patterns, and 15+ migration patterns. Covers monolith, modular monolith, microservices, event-driven, serverless, and hybrid architectures. Actions: design, review, plan, document, decide, migrate. Topics: system design, architecture patterns, ADRs, scalability, reliability, security, integration, migration, trade-offs, NFRs."
license: MIT
compatibility: opencode
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: architecture
  triggers: architecture, system design, ADR, microservices, scalability, trade-off, tech decision, monolith, event-driven, CQRS, saga, patterns, NFR, migration, distributed systems
  role: expert
  scope: design
  output-format: document + diagram
  related-skills: backend-developer, frontend-developer, security-engineer, devops-engineer, test-master
---

# Architecture Designer Pro — System Engineering

Principal architect specializing in distributed systems, design patterns, scalability, reliability, and architectural decision-making. Covers all architecture styles and patterns.

## Architecture Decision Matrix

| Style | Team Size | Scalability | Complexity | Time to Market | When to Choose |
|-------|-----------|-------------|------------|----------------|----------------|
| **Monolith** | 1-5 | Low | Low | Fastest | Startup, prototype, small team |
| **Modular Monolith** | 3-10 | Medium | Medium | Fast | Growing team, clear domain boundaries |
| **Microservices** | 5+ per service | High | High | Slow | Large team, independent deployability |
| **Event-Driven** | 3+ | High | High | Medium | Async workflows, audit trail, integration |
| **Serverless** | 1-5 | Auto-scaling | Low | Fastest | Event processing, variable load |
| **Service Mesh** | 10+ | High | Very High | Slow | Enterprise, multi-service communication |

## Quick Reference — 12 Priority Categories

### 1. Requirements Gathering (CRITICAL)

| Category | Questions | Must Document |
|----------|-----------|---------------|
| **Functional** | What does the system do? Who are the users? What are the flows? | Use cases, user stories, domain model |
| **Performance** | Expected RPS? P95 latency? Data volume? | Throughput, response time, data size |
| **Availability** | Required uptime? RTO? RPO? | 99.9% (8h/yr) vs 99.99% (52min/yr) |
| **Scalability** | Growth projection? Traffic patterns? | Current + 2x, 10x, 100x scenarios |
| **Security** | Compliance (SOC2/PCI/GDPR)? Auth model? Data sensitivity? | Security requirements, threat model |
| **Cost** | Budget? Team size? Timeline? | Infrastructure, licensing, team cost |
| **Constraints** | Tech stack? Cloud provider? Team skills? | Immutable constraints, negotiable constraints |

### 2. Architecture Pattern Selection (CRITICAL)

| Pattern | When | When NOT | Trade-offs |
|---------|------|----------|------------|
| **Modular Monolith** | Small team, clear bounded contexts, < 5 services | Need independent scaling, team-per-service | Simple ops, limited scaling |
| **Microservices** | Independent deployability, team-per-service, polyglot | Small team, simple domain, no clear boundaries | Operational complexity, data consistency |
| **Event-Driven** | Async workflows, audit trail, loose coupling | Simple CRUD, strong consistency needed | Eventual consistency, debugging |
| **CQRS** | Different read/write models, complex queries | Simple CRUD, single model suffices | Write complexity, eventual consistency |
| **Event Sourcing** | Full audit trail, temporal queries, complex state | Simple CRUD, storage is cheap | Storage, event schema evolution |
| **Saga** | Distributed transaction, long-running business process | Simple transaction, single service | Compensation complexity, testing |
| **Strangler Fig** | Incremental monolith → microservices migration | Greenfield project | Running two systems during migration |
| **Backend for Frontend** | Different client types (web, mobile, API) | Single client type | Code duplication across BFFs |
| **API Gateway** | Cross-cutting concerns (auth, rate limit, routing) | Single service, simple routing | Latency, single point of failure |
| **Sidecar** | Cross-cutting concerns per service (logging, proxy) | Large number of services | Resource overhead |

### 3. Data Architecture (HIGH)

| Concern | Pattern | Implementation |
|---------|---------|----------------|
| **Database per service** | Each service owns its data | No shared DB between services |
| **Eventually consistent** | Accept stale reads for availability | Eventual consistency > strong for most cases |
| **CQRS** | Separate read/write models | Read models optimized for queries |
| **Event Sourcing** | Store events, derive state | Append-only event store |
| **Saga** | Distributed transaction with compensation | Choreography (events) or Orchestration (coordinator) |
| **Materialized views** | Pre-computed query results | Refresh on event or schedule |
| **Change Data Capture** | Stream DB changes to other services | Debezium, AWS DMS |
| **Soft deletes** | Never hard delete, use `deleted_at` | Data recovery, audit trail |

```typescript
// Event-sourced aggregate
interface Event {
  type: string
  data: unknown
  timestamp: Date
  version: number
}

class OrderAggregate {
  private events: Event[] = []
  private state: { status: string; items: string[] } = { status: 'pending', items: [] }

  constructor(events: Event[]) {
    this.events = events
    for (const event of events) {
      this.apply(event)
    }
  }

  addItem(itemId: string) {
    this.events.push({
      type: 'ItemAdded',
      data: { itemId },
      timestamp: new Date(),
      version: this.state.version + 1,
    })
    this.apply(this.events[this.events.length - 1])
  }

  private apply(event: Event) {
    switch (event.type) {
      case 'ItemAdded':
        this.state.items.push(event.data.itemId)
        break
      // ...
    }
  }
}
```

### 4. API & Integration (HIGH)

| Pattern | Protocol | When | Don't |
|---------|----------|------|-------|
| **REST** | HTTP/JSON | CRUD, resource-oriented, simple | Complex querying, real-time |
| **GraphQL** | HTTP/GraphQL | Flexible queries, multiple clients | File uploads, simple CRUD |
| **gRPC** | HTTP/2, Protobuf | Internal services, high performance | Browser clients (without proxy) |
| **WebSocket** | TCP/bidirectional | Real-time, notifications, chat | Request-response APIs |
| **Message Queue** | AMQP/Kafka | Async processing, event distribution | Synchronous request-response |
| **Webhook** | HTTP callback | Event notifications to external systems | Reliability without retry |

```typescript
// Internal service communication: gRPC
service OrderService {
  rpc CreateOrder (CreateOrderRequest) returns (OrderResponse);
  rpc GetOrder (GetOrderRequest) returns (OrderResponse);
  rpc ListOrders (ListOrdersRequest) returns (ListOrdersResponse);
}

// Event-driven: Kafka topic naming
// <domain>.<event>.<version>
const TOPIC = 'order.created.v1'
```

### 5. Scalability (HIGH)

| Dimension | Strategy | Implementation |
|-----------|----------|----------------|
| **Compute** | Horizontal scaling (add instances) | Auto-scaling group, stateless design |
| **Database** | Read replicas, sharding, caching | Replicas first, then cache, then shard |
| **Cache** | Multi-layer: CDN → app cache → DB cache | CloudFront → Redis → DB |
| **Async** | Queue + worker pattern | SQS + Lambda / Bull + Node |
| **Static content** | CDN for everything static | CloudFront, Cloudflare, Fastly |
| **Database queries** | Optimize + cache + paginate | N+1 prevention, cursor pagination |
| **Image processing** | Async + optimized formats | Queue → resize → WebP → CDN |

```typescript
// Stateless service — horizontal scaling ready
// NO: session in memory, local file storage, sticky sessions
// YES: session in Redis, S3 for files, shared-nothing

// Cache-aside pattern
async function getUser(id: string): Promise<User> {
  const cached = await redis.get(`user:${id}`)
  if (cached) return JSON.parse(cached)

  const user = await db.user.findUnique({ where: { id } })
  if (user) {
    await redis.setex(`user:${id}`, 300, JSON.stringify(user)) // 5min TTL
  }
  return user
}
```

### 6. Reliability & Resilience (HIGH)

| Pattern | Problem | Solution |
|---------|---------|----------|
| **Retry** | Transient failures | Exponential backoff with jitter: `delay = min(cap, base * 2^n + random(0, jitter))` |
| **Circuit Breaker** | Cascading failures | Open after N failures, half-open after timeout, close on success |
| **Bulkhead** | Resource exhaustion | Isolate thread pools/connections per dependency |
| **Timeout** | Hanging dependencies | `AbortSignal.timeout(5000)` for every external call |
| **Fallback** | Non-critical dependency failure | Return cached/default data, degrade gracefully |
| **Rate Limiter** | Client overuse | Token bucket: 100 req/s, 200 burst |
| **Health Check** | Unhealthy instances | Liveness (alive?) + Readiness (accept traffic?) |
| **Graceful Shutdown** | In-flight request loss | SIGTERM → drain → stop |

```typescript
// Circuit breaker
import CircuitBreaker from 'opossum'

const breaker = new CircuitBreaker(api.callExternalService, {
  timeout: 5000,
  errorThresholdPercentage: 50,  // Open after 50% errors
  resetTimeout: 30000,            // Try half-open after 30s
  volumeThreshold: 10,            // Min requests before tripping
})

breaker.fallback(() => cachedData)
breaker.on('open', () => logger.warn('Circuit opened for external service'))
breaker.on('halfOpen', () => logger.info('Circuit half-open'))
breaker.on('close', () => logger.info('Circuit closed'))

// Usage
const result = await breaker.fire(requestData)
```

### 7. Security Architecture (HIGH)

| Concern | Pattern | Implementation |
|---------|---------|----------------|
| **Auth** | OAuth 2.0 + OIDC | Centralized identity provider, PKCE for SPA |
| **API auth** | JWT or mTLS | Short-lived JWT for internal, mTLS for service-to-service |
| **Secrets** | Centralized secret manager | HashiCorp Vault, AWS Secrets Manager |
| **Network** | Zero trust | mTLS between services, no network trust |
| **Audit** | Immutable audit log | Append-only event store for security events |
| **Data** | Encrypt at rest + in transit | AES-256, TLS 1.3 |
| **Compliance** | Automated compliance checks | SOC 2, PCI DSS, GDPR, HIPAA |

### 8. Deployment Architecture (MEDIUM)

| Pattern | Complexity | Downtime | Rollback | When |
|---------|------------|----------|----------|------|
| **Rolling update** | Low | Zero | Slow | Default |
| **Blue/Green** | Medium | Zero | Instant | Critical production services |
| **Canary** | High | Zero | Instant | Risk-averse, gradual rollout |
| **Feature flags** | Low | Zero | Instant | Any deployment |
| **Shadow** | High | Zero | N/A | Testing with production traffic |

```yaml
# Canary release: 10% traffic to new version
apiVersion: flagger.app/v1beta1
kind: Canary
metadata:
  name: api
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  service:
    port: 80
  analysis:
    interval: 1m
    threshold: 5
    maxWeight: 50
    stepWeight: 10
    metrics:
      - name: request-success-rate
        thresholdRange: { min: 99 }
      - name: request-duration
        thresholdRange: { max: 500 }
```

### 9. Observability (MEDIUM)

| Pillar | Tool | What | Alert |
|--------|------|------|-------|
| **Logs** | Structured JSON | All requests, errors, debug info | ERROR rate > baseline |
| **Metrics** | Prometheus + Grafana | RPS, latency, error rate, saturation | P95 > 500ms, errors > 1% |
| **Traces** | OpenTelemetry + Jaeger | Request flow across services | Span error rate > 5% |
| **Profiling** | pprof / pyroscope | CPU, memory, goroutine leaks | Memory > 80% heap limit |
| **Audit** | Immutable audit log | Auth events, data changes, config changes | Unauthorized access attempt |

### 10. Testing Architecture (MEDIUM)

| Level | Responsibility | Tooling | CI Stage |
|-------|---------------|---------|----------|
| **Unit** | Individual functions, services | Vitest/Jest/pytest | Every commit |
| **Integration** | Service boundaries, DB, API | Supertest, Testcontainers | Every PR |
| **Contract** | Service-to-service compatibility | Pact, Spring Cloud Contract | Deploy to staging |
| **E2E** | Critical user journeys | Playwright, Cypress | Main branch |
| **Load** | Performance, breaking point | k6, Locust | Pre-release |
| **Chaos** | Resilience, failure handling | Chaos Mesh, Gremlin | Production (off-peak) |

### 11. Migration Patterns (MEDIUM)

| Scenario | Pattern | Steps |
|----------|---------|-------|
| **Monolith → Microservices** | Strangler Fig | 1. Identify bounded context 2. Extract service 3. Route traffic 4. Remove old code |
| **Database migration** | Expand → Migrate → Contract | 1. Add new schema (nullable) 2. Dual-write 3. Backfill 4. Switch reads 5. Remove old |
| **Technology migration** | Parallel run + comparison | 1. Run both systems 2. Compare outputs 3. Switch at parity 4. Decommission old |
| **Cloud migration** | Lift-shift → Optimize | 1. Re-host as-is 2. Measure 3. Optimize (RDS, S3, etc.) 4. Refactor |

### 12. ADR (Architecture Decision Record) (MEDIUM)

Every significant architecture decision gets an ADR.

```markdown
# ADR-001: Use PostgreSQL for Primary Database

## Status
Accepted

## Context
We need a primary database for the new e-commerce platform.
Requirements: strong consistency, complex queries, JSON support,
ACID transactions, 99.95% availability, max 50ms query latency.

## Decision
Use PostgreSQL 16 with the following configuration:
- Multi-AZ deployment (RDS Aurora)
- Read replicas for reporting queries
- JSONB for flexible product attributes
- pgvector for search embeddings (future)

## Alternatives Considered

### Option A: MySQL 8
- Pros: Mature, widely known, cheaper RDS
- Cons: Weaker JSON support, no pgvector, fewer extensions

### Option B: MongoDB 7
- Pros: Schema-less, horizontal scaling, great for catalog
- Cons: No ACID transactions for orders, eventual consistency,
  weaker joins for reporting

### Option C: CockroachDB
- Pros: Auto-scaling, strong consistency, multi-region
- Cons: Less mature ecosystem, higher cost, team unfamiliar

## Consequences
- Positive: ACID compliance for orders, JSON for product flexibility,
  pgvector for future AI features
- Negative: Need connection pooling (PgBouncer), read replicas for scale
- Neutral: Team needs PostgreSQL training

## Compliance
- All queries must use parameterized statements
- Migrations reviewed for performance impact (EXPLAIN ANALYZE)
- Connection pooling configured for >100 concurrent connections
```

## Pre-Architecture Review Checklist

### Requirements
- [ ] Functional requirements documented with use cases
- [ ] Non-functional requirements defined (latency, availability, durability, compliance)
- [ ] Constraints documented (team size, budget, timeline, tech stack)
- [ ] Data volume and growth projections estimated
- [ ] Security and compliance requirements identified

### Design
- [ ] Architecture pattern selected with explicit trade-off justification
- [ ] Component diagram created (containers, services, data stores)
- [ ] Data flow documented (request/response, events, jobs)
- [ ] Failure modes analyzed (what happens when each component fails)
- [ ] Scalability strategy defined (horizontal, vertical, caching)

### Decisions
- [ ] Every significant choice documented with ADR
- [ ] At least 2 alternatives evaluated per decision
- [ ] Trade-offs explicitly documented (cost, complexity, operational burden)
- [ ] Security review completed for architectural decisions
- [ ] Cost estimate prepared (infrastructure, licensing, operations)

### Operations
- [ ] Deployment strategy defined (rolling, blue/green, canary)
- [ ] Rollback procedure documented
- [ ] Monitoring and alerting planned
- [ ] Incident response runbook outlined
- [ ] Backup and disaster recovery plan documented

## Knowledge Reference

- Architectural patterns: Monolith, Modular, Microservices, Event-Driven, Serverless, Service Mesh
- Design patterns: CQRS, Event Sourcing, Saga, Strangler Fig, BFF, API Gateway, Sidecar, Ambassador
- Data patterns: Database per Service, CQRS, Event Sourcing, Saga, CDC, Materialized Views
- Integration: REST, GraphQL, gRPC, WebSocket, Message Queue, Kafka, RabbitMQ
- Deployment: Rolling, Blue/Green, Canary, Feature Flags, Shadow
- Reliability: Retry, Circuit Breaker, Bulkhead, Timeout, Fallback, Rate Limiter
- C4 Model (Context, Container, Component, Code), UML
- TOGAF, Zachman, ISO 42010
- Cloud: AWS Well-Architected Framework, GCP Architecture Framework, Azure CAF
- SRE: SLIs/SLOs/SLAs, Error Budgets, Toil Reduction
- Distributed Systems: CAP Theorem, PACELC, Consistency Models, Consensus Algorithms
