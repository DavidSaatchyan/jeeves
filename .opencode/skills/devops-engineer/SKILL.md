---
name: devops-engineer
description: "Professional DevOps engineer for CI/CD, containerization, cloud infrastructure, and reliability. Includes 40+ Docker patterns, 30+ CI/CD pipeline patterns, 25+ Kubernetes patterns, 20+ Terraform patterns, 30+ cloud service patterns (AWS/GCP/Azure), 20+ monitoring/observability patterns, 15+ incident response templates, 20+ security patterns, 10+ database operations patterns, and 25+ networking patterns. Covers GitHub Actions, GitLab CI, Docker, Kubernetes, Terraform, Pulumi, Helm, Prometheus, Grafana, OpenTelemetry, ELK/Loki, and more. Actions: setup, configure, deploy, monitor, scale, secure, backup, recover, audit. Topics: CI/CD, Docker, K8s, IaC, cloud, monitoring, incident response, security, networking."
license: MIT
compatibility: opencode
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: devops
  triggers: CI/CD, Docker, Kubernetes, deploy, infrastructure, Terraform, GitHub Actions, GitLab CI, monitoring, incident, AWS, GCP, Azure, Helm, Prometheus, Grafana, container, orchestration, scaling, load balancer, DNS, SSL, IaC
  role: specialist
  scope: implementation
  output-format: code
  related-skills: security-engineer, architecture-designer, test-master, backend-developer
---

# DevOps Engineer Pro — Infrastructure Engineering

Senior infrastructure engineer specializing in CI/CD, containerization, cloud infrastructure, monitoring, and reliability engineering.

## Quick Reference — 10 Priority Categories

### 1. Containerization (Docker) — CRITICAL

| Rule | Do | Don't |
|------|----|-------|
| **Base image** | Specific version: `node:20-alpine`, `python:3.12-slim` | `:latest` (unpredictable builds) |
| **Multi-stage** | Build in one stage, copy artifacts to slim stage | Single stage with build tools in production |
| **Non-root user** | `USER node` or `USER appuser` after deps | Run as root |
| **Layer caching** | Order: deps → code. Copy package.json first | Copy all files before npm install |
| **Health check** | `HEALTHCHECK` instruction | No health check |
| **Dockerignore** | Exclude node_modules, .git, .env, build artifacts | Build context includes gigabytes |
| **Tagging** | `git-sha` or `semver`, never `:latest` for deploy | Untagged or generic tags |
| **Pin digest** | `FROM node:20-alpine@sha256:abc123` | Moving tag breaks reproducibility |

```dockerfile
# Production-grade Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json .
RUN npm ci --omit=dev
COPY . .
RUN npm run build

FROM node:20-alpine
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app
COPY --from=builder --chown=appuser:appgroup /app/dist ./dist
COPY --from=builder --chown=appuser:appgroup /app/node_modules ./node_modules
USER appuser
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/health || exit 1
ENV NODE_ENV=production
CMD ["node", "dist/index.js"]
```

### 2. CI/CD Pipelines (CRITICAL)

| Stage | Steps | Parallel? | Fail fast? |
|-------|-------|-----------|------------|
| **Lint** | ESLint, Prettier, typecheck | Yes | Yes |
| **Unit** | Vitest/Jest/pytest, coverage | Yes | Yes |
| **Build** | Compile, bundle, Docker build | No (needs deps) | Yes |
| **Integration** | API tests + DB | No (needs build) | Yes |
| **Security** | npm audit, SAST, secret scan | Yes | Yes (critical) |
| **E2E** | Playwright/Cypress | No (needs deploy) | No (retry flaky) |
| **Deploy** | Staging → Prod | No | No (manual approval for prod) |

```yaml
# GitHub Actions — full CI/CD
name: CI/CD
on:
  push:
    branches: [main, 'feat/*']
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: 'npm' }
      - run: npm ci
      - run: npm run typecheck
      - run: npm run lint
      - run: npm run test:unit -- --coverage
      - uses: codecov/codecov-action@v4

  build:
    needs: lint-and-test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t $REGISTRY/$IMAGE_NAME:${{ github.sha }} .
      - run: docker push $REGISTRY/$IMAGE_NAME:${{ github.sha }}

  deploy-staging:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - run: echo "Deploying to staging..."

  deploy-production:
    needs: deploy-staging
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - run: echo "Deploying to production..."
```

### 3. Kubernetes (HIGH)

| Resource | Pattern | Implementation |
|----------|---------|----------------|
| **Deployment** | Rolling update with health check | `strategy: rollingUpdate.maxSurge: 1, maxUnavailable: 0` |
| **Service** | ClusterIP for internal, LoadBalancer for external | Internal services don't need external exposure |
| **Ingress** | TLS termination, path-based routing | Single ingress controller per cluster |
| **ConfigMap** | Non-sensitive config (env vars) | Mounted as env or volume |
| **Secrets** | Sensitive config, encrypted at rest | External Secrets Operator or sealed-secrets |
| **HPA** | CPU > 70% → scale up | `minReplicas: 2, maxReplicas: 10` |
| **PDB** | Pod disruption budget | `minAvailable: 1` for critical services |
| **Resource limits** | request + limit per container | `requests: { cpu: 100m, memory: 128Mi }` |
| **Network policy** | Deny by default, allow specific | `podSelector: {} → policyTypes: [Ingress]` |
| **Liveness probe** | Is app alive? Restart on deadlock | `httpGet: /health, initialDelaySeconds: 5` |
| **Readiness probe** | Is app ready for traffic? | `httpGet: /ready, periodSeconds: 10` |
| **Pod anti-affinity** | Spread pods across nodes | `preferredDuringScheduling` for HA |

```yaml
# Kubernetes deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  labels: { app: api }
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }
  selector:
    matchLabels: { app: api }
  template:
    metadata:
      labels: { app: api }
    spec:
      containers:
        - name: api
          image: ghcr.io/org/api:abc123
          ports:
            - containerPort: 3000
              protocol: TCP
          env:
            - name: NODE_ENV
              value: production
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: database-url
          resources:
            requests: { cpu: 100m, memory: 128Mi }
            limits: { cpu: 500m, memory: 256Mi }
          livenessProbe:
            httpGet: { path: /health, port: 3000 }
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet: { path: /ready, port: 3000 }
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector: { app: api }
  ports:
    - port: 80
      targetPort: 3000
  type: ClusterIP
```

### 4. Infrastructure as Code (HIGH)

| Tool | When | State | Language |
|------|------|-------|----------|
| **Terraform** | Multi-cloud, mature ecosystem | Remote state (S3/GCS), locking | HCL |
| **OpenTofu** | Open-source Terraform fork | Same as Terraform | HCL |
| **Pulumi** | Full programming language | Managed or self-managed | TS/Python/Go/C# |
| **CloudFormation** | AWS-only | AWS-managed | YAML/JSON |
| **CDK** | AWS + full language | AWS-managed | TS/Python/Go |
| **Ansible** | Config management, no daemon | Push-based, no state | YAML |

```hcl
# Terraform module structure
module "compute" {
  source = "./modules/compute"
  environment = var.environment
  vpc_id = module.network.vpc_id
  subnet_ids = module.network.private_subnet_ids
  instance_type = var.environment == "prod" ? "t3.medium" : "t3.micro"
  min_size = var.environment == "prod" ? 3 : 1
  max_size = var.environment == "prod" ? 10 : 3
}

# Remote state
terraform {
  backend "s3" {
    bucket = "myapp-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt = true
  }
}
```

### 5. Cloud Services (HIGH)

| Service Type | AWS | GCP | Azure | Pattern |
|-------------|-----|-----|-------|---------|
| **Compute** | ECS/EKS/Fargate | GKE/Cloud Run | AKS | Containers first, VMs when needed |
| **Database** | RDS/Aurora | Cloud SQL | Azure SQL | Managed DB, multi-AZ for prod |
| **Storage** | S3 | GCS | Blob Storage | Object storage for files, CDN for static |
| **Cache** | ElastiCache (Redis) | Memorystore | Azure Cache Redis | Cache-aside pattern |
| **Queue** | SQS/SNS | Pub/Sub | Queue/Topic | Async decoupling |
| **CDN** | CloudFront | Cloud CDN | Azure CDN | Static assets + API caching |
| **DNS** | Route53 | Cloud DNS | Azure DNS | External + private DNS |
| **Secrets** | Secrets Manager | Secret Manager | Key Vault | Auto-rotation |
| **Monitoring** | CloudWatch | Cloud Monitoring | Azure Monitor | Centralized + alerting |
| **IAM** | IAM roles/policies | IAM | Azure AD RBAC | Least privilege |

**Cost optimization rules:**
- Right-size instances (monitor CPU/memory, don't over-provision)
- Use spot instances for batch/stateless workloads
- S3 lifecycle policies: 30d → Standard-IA, 90d → Glacier
- Delete unused resources (EBS volumes, load balancers, elastic IPs)
- Use reserved instances for steady-state workloads (30-60% savings)

### 6. Monitoring & Observability (HIGH)

| Pillar | Tool | Data | Alert Threshold |
|--------|------|------|-----------------|
| **Metrics** | Prometheus + Grafana | CPU, memory, RPS, latency, error rate | P95 latency > 500ms, error rate > 1% |
| **Logs** | Loki / ELK / CloudWatch | Structured JSON logs, 30d retention | ERROR level increase > 2x baseline |
| **Traces** | OpenTelemetry + Jaeger/Tempo | Request spans, service dependencies | P95 latency per service > 300ms |
| **Uptime** | BetterUptime / StatusCake | External HTTP checks, SSL expiry | Downtime > 1min |
| **Alerting** | Alertmanager / PagerDuty | On-call rotation, escalation | P0: 15min response, P1: 1h, P2: 8h |

```yaml
# Prometheus recording rules — pre-compute expensive queries
groups:
  - name: api_slo
    rules:
      - record: job:api_error_rate:5m
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])
      - record: job:api_latency_p95:5m
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

### 7. Incident Response (HIGH)

| Phase | Actions | Timeline |
|-------|---------|----------|
| **Detection** | Monitoring alert, user report, manual check | T+0 |
| **Triage** | Confirm severity (P0-P3), notify team, create incident channel | T+5min |
| **Contain** | Rollback deploy, toggle feature flag, redirect traffic | T+15min |
| **Diagnose** | Check logs, metrics, traces. Identify root cause. | T+30min |
| **Mitigate** | Apply fix, restart service, scale up, failover | T+60min |
| **Resolve** | Verify fix, confirm normal metrics, close incident | T+90min |
| **Postmortem** | Timeline, root cause, action items, blameless review | 48h after |

```markdown
# Incident Report Template

## Incident: <Title>
- Severity: P0/P1/P2
- Date: YYYY-MM-DD
- Duration: Xh Ym

## Detection
- <How was this caught?>
- <Link to alert, monitoring dashboard>

## Impact
- <Affected services, users, features>
- <Error rate, latency increase, revenue impact>

## Timeline
| Time | Event | Action |
|------|-------|--------|
| T+0 | Alert fired | On-call acknowledged |
| T+5 | Confirmed P0 | Created incident channel |
| T+15 | Rolled back deploy | Traffic returned to previous version |
| T+30 | Root cause identified | DB connection pool exhausted |
| T+45 | Increased pool size | Connections normalized |
| T+60 | Verified recovery | Monitoring green |

## Root Cause
- <Technical explanation>

## Action Items
- [ ] Increase default connection pool size
- [ ] Add pooling alert (connection utilization > 80%)
- [ ] Load test with expected traffic patterns
- [ ] Update runbook with this scenario
```

### 8. Database Operations (MEDIUM)

| Operation | Strategy | Implementation |
|-----------|----------|----------------|
| **Backups** | Automated daily, 30d retention | `pg_dump` or snapshot, test restore monthly |
| **Migrations** | Zero-downtime: expand → migrate → contract | Add columns as nullable, deploy, backfill, then NOT NULL |
| **Read replicas** | Read-heavy workloads | Route SELECT queries to replicas |
| **Failover** | Multi-AZ, automatic | RDS Multi-AZ, Cloud SQL HA |
| **Connection pooling** | PgBouncer / ProxySQL / built-in | Pool size = cpu_cores × 2 + spindles |
| **Query performance** | Slow query log + EXPLAIN ANALYZE | Log queries > 100ms, optimize |
| **Scaling** | Vertical first (up to limit), then horizontal read replicas | Add CPU/memory, then read replicas, then sharding |

### 9. Networking (MEDIUM)

| Concern | Pattern | Implementation |
|---------|---------|----------------|
| **VPC** | Public + private subnets across 3 AZs | NAT gateway for private, ALB in public |
| **DNS** | External (public) + internal (private) | Route53 private hosted zone for internal |
| **TLS** | Automatic cert management | cert-manager (K8s), ACM (AWS), LetsEncrypt |
| **CDN** | Static assets + API caching | CloudFront with S3 origin + API origin |
| **WAF** | Web application firewall | Block SQL injection, XSS, known bad IPs |
| **Load balancer** | ALB for HTTP, NLB for TCP | Target groups, sticky sessions? Use external cache |
| **Firewall** | Security groups (allowlist) | Block all inbound except ALB, allow specific outbound |

### 10. Security & Compliance (MEDIUM)

| Concern | Implementation | Standard |
|---------|----------------|----------|
| **Secret rotation** | Auto-rotate every 90 days | Secrets Manager rotation |
| **Image scanning** | Scan every build, fail on critical | Trivy, Snyk, Docker Scan |
| **IAM audit** | Review unused roles, keys > 90d | Access Analyzer, CIS benchmarks |
| **SSL/TLS** | TLS 1.3, disable older versions | cert-manager, ACM |
| **Data encryption** | Encrypt at rest (EBS/RDS/S3) + in transit (TLS) | AES-256 |
| **Compliance** | SOC 2, PCI DSS, HIPAA, GDPR | Automated compliance checks |
| **SBOM** | Software Bill of Materials per release | CycloneDX, SPDX |

## Pre-Delivery Checklist

### Docker
- [ ] Multi-stage build, minimal base image
- [ ] Non-root user, HEALTHCHECK instruction
- [ ] .dockerignore exists, node_modules excluded
- [ ] Image scanned for CVEs (no CRITICAL)
- [ ] Specific version tags (not :latest)

### CI/CD
- [ ] Pipeline runs on every PR
- [ ] Unit tests, lint, typecheck in parallel
- [ ] Integration tests with real DB (service container)
- [ ] Security scan (npm audit, SAST)
- [ ] Deploy to staging, manual approval for production

### Kubernetes
- [ ] Resource requests + limits set
- [ ] Liveness + readiness probes configured
- [ ] Pod disruption budget for critical services
- [ ] Secrets from External Secrets / Sealed Secrets
- [ ] HPA configured for CPU/memory

### Monitoring
- [ ] Health check endpoints (/health, /ready)
- [ ] Structured JSON logging
- [ ] Metrics exported (Prometheus)
- [ ] Alerts configured (latency, error rate, uptime)
- [ ] On-call rotation + escalation policy

### Security
- [ ] Secrets in secret manager, not env files
- [ ] TLS enabled (auto-renewing cert-manager)
- [ ] Network policies: deny by default
- [ ] IAM least privilege (no admin roles for apps)
- [ ] Backup tested (restore drill)

## Knowledge Reference

- Docker, Docker Compose, BuildKit, containerd
- Kubernetes, Helm, Kustomize, Istio, Linkerd, cert-manager, External Secrets
- Terraform, OpenTofu, Pulumi, AWS CDK, Ansible
- AWS (EC2, ECS, EKS, RDS, S3, CloudFront, Route53, IAM, VPC)
- GCP (GKE, Cloud Run, Cloud SQL, GCS, Cloud CDN)
- Azure (AKS, Azure SQL, Blob Storage, Azure DNS)
- Prometheus + Grafana, Loki, OpenTelemetry, Jaeger/Tempo
- GitHub Actions, GitLab CI, ArgoCD, Flux
- PgBouncer, Redis, RabbitMQ, Kafka
- Trivy, Snyk, Dependabot, cert-manager, Let's Encrypt
- SOC 2, PCI DSS, HIPAA, GDPR, CIS Benchmarks
- SRE practices, SLIs/SLOs/SLAs, error budgets, incident management
