# Production Deployment Checklist — Jeeves

## 1. Environments

### 1.1 Environment Tiers
- [ ] **Production** — Railway `main` branch, auto-deploy, real data
- [ ] **Staging** — Railway `staging` branch or separate Railway project (mirrors production)
- [ ] **Development** — local `uvicorn --reload` with SQLite or local PostgreSQL
- [ ] **PR previews** — Railway ephemeral environments per PR (optional)

### 1.2 Staging Requirements
- [ ] Staging uses a separate Railway project with its own PostgreSQL and Chroma volumes
- [ ] Staging has its own OpenAI API key (or uses a separate usage tier)
- [ ] Staging env vars are independent of production
- [ ] Staging points at test/sandbox Shopify, Recharge, Stripe accounts
- [ ] Staging email delivery uses sandbox mode (SendGrid test mode / Resend sandbox)

### 1.3 Railway Project Configuration
- [ ] Deployment source: GitHub repo `https://github.com/DavidSaatchyan/jeeves`
- [ ] Root directory: `/` (Dockerfile is at root)
- [ ] Build command: default (Dockerfile)
- [ ] Start command: default (`uvicorn app.main:app --host 0.0.0.0 --port 8000`)

### 1.4 Worker Containers (Separate Services in Railway)
- [ ] **API service** — `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- [ ] **Scheduler worker** — `python -m app.workers.scheduler` (env `WORKER_TYPE=scheduler`)
- [ ] **Event worker** — `python -m app.workers.event_worker` (env `WORKER_TYPE=event`)
- [ ] **Workflow worker** — `python -m app.workers.workflow_worker` (env `WORKER_TYPE=workflow`)
- [ ] **Comms worker** — `python -m app.workers.comms_worker` (env `WORKER_TYPE=comms`)

---

## 2. Databases

### 2.1 PostgreSQL (Railway Managed)
- [ ] Provisioned via Railway Dashboard → New → Database → PostgreSQL
- [ ] Version: PostgreSQL 15+
- [ ] `DATABASE_URL` auto-injected by Railway into connected services
- [ ] Connection pool: `pool_pre_ping=True` (already set in `db.py`)
- [ ] SSL connection enforced (`sslmode=require`)
- [ ] Automated daily backups enabled (Railway managed — verify in dashboard)
- [ ] Point-in-time recovery configured if available
- [ ] Database has sufficient storage for: tenants + customers + subscriptions + invoices + workflows + chat logs + timeline events

### 2.2 Redis (Production)
- [ ] Provisioned via Railway Dashboard → New → Database → Redis (or external Redis provider)
- [ ] `REDIS_URL` set in environment variables with `ssl_cert_reqs=required` for `rediss://` URLs
- [ ] Redis used for:
  - [ ] Rate limiting (`shared/queue.py`)
  - [ ] Token denylist (`auth.py` — `revoked:*` keys)
  - [ ] Workflow scheduling (`core/workflows/scheduler.py` — sorted sets)
  - [ ] Async task queue (`shared/queue.py` — Redis lists)
  - [ ] In-memory fallback path tested (app must not crash when Redis is unavailable)
- [ ] Redis eviction policy: `noeviction` or `volatile-lru` (scheduled jobs use TTL)
- [ ] Redis persistence: RDB snapshots enabled at minimum

### 2.3 ChromaDB (Vector Store)
- [ ] Persistent Volume mounted at `/data/chroma`
- [ ] Volume size: 1 GB minimum (adjust based on expected KB document count)
- [ ] `CHROMA_PATH=/data/chroma` set in environment
- [ ] No automatic backup for Chroma — plan for periodic export
- [ ] Vector dimension matches `text-embedding-3-small` (1536 dimensions)
- [ ] Collection naming: `tenant_{uuid_nodashes}`
- [ ] Tested reindex from scratch (can regenerate from knowledge files if volume is lost)

### 2.4 Database Migrations (Alembic)
- [ ] Latest migration applied and tested against staging
- [ ] `alembic.ini` points to correct migration directory
- [ ] Auto-migration on startup has safety bypass for JSONB → JSON (SQLite dev compat)
- [ ] Migration tested as non-destructive (no data loss on existing tables)
- [ ] Rollback migration exists for each new change
- [ ] Migration lock prevents concurrent applies (only one container runs migrations)

---

## 3. Secrets

### 3.1 Production Secrets (Railway Variables)
| Variable | Source | Validation |
|----------|--------|------------|
| `DATABASE_URL` | Railway auto-injected | Verified by `health/db` endpoint |
| `OPENAI_API_KEY` | OpenAI dashboard | Tested with `curl` to OpenAI API |
| `JWT_SECRET` | Generated (64+ char random) | Validated at startup: min 32 chars |
| `FERNET_KEY` | Generated (44 base64 or 32+ char) | Validated at startup: min 32 chars |
| `STRIPE_SECRET_KEY` | Stripe dashboard | Tested with Stripe API call |
| `SENDGRID_API_KEY` | SendGrid dashboard | Tested with SendGrid send call |
| `RESEND_API_KEY` | Resend dashboard | Alternative to SendGrid |
| `RECHARGE_API_KEY` | Recharge dashboard | Tested with Recharge API call |
| `SHOPIFY_ACCESS_TOKEN` | Shopify admin | Tested with Shopify API call |
| `SHOPIFY_SHOP` | Shopify admin | Valid domain format |

### 3.2 Secret Rotation Policy
- [ ] JWT_SECRET rotated immediately if compromised
- [ ] OpenAI API keys rotated quarterly
- [ ] Stripe/Recharge/Shopify credentials rotated on staff change
- [ ] Fernet key rotation requires re-encryption of stored credentials
- [ ] Old API keys (sk_*) can be revoked via admin panel without redeploy

### 3.3 Secret Validation at Startup
- [ ] Required secrets crash the app with descriptive message if missing (implemented in `config.py:_validate_secrets()`)
- [ ] Known default values are detected and rejected (e.g., `dev-secret-change-me`)
- [ ] JWT secret minimum length enforced (32 chars)
- [ ] Fernet key length warning logged if too short

### 3.4 `.env` File Safety
- [ ] `.env` is in `.gitignore` — never committed
- [ ] `.env.example` has placeholder values (sk-..., your-password)
- [ ] No real secrets in any environment file

---

## 4. Backups

### 4.1 PostgreSQL Backups
- [ ] Railway automated backups enabled (daily)
- [ ] Verify backup retention period (Railway default: 7 days — adjust if needed)
- [ ] Manual backup taken before major schema migrations
- [ ] Documented restore procedure:
  ```
  Railway Dashboard → PostgreSQL → Backups → Restore
  ```
- [ ] Test restore to a staging environment at least once

### 4.2 ChromaDB Backups
- [ ] Chroma volume is NOT automatically backed up by Railway
- [ ] Mitigation: knowledge files can be re-uploaded to rebuild Chroma collections
- [ ] Periodic backup script considered (copy `/data/chroma` to S3 via cron)
- [ ] `rag.py` has `deduplicate_collection()` and `purge_orphans()` for recovery

### 4.3 Knowledge Files Backup
- [ ] Knowledge files stored on ephemeral filesystem — lost on redeploy
- [ ] Plan to migrate to S3 or Railway Volume (same as Chroma)
- [ ] Current state: embeddings survive in Chroma, files must be re-uploaded on restart

### 4.4 Config Backup
- [ ] `config.yaml` — gitignored (contains runtime config), backed up separately
- [ ] Tenant `PolicySet` data in PostgreSQL (safe)
- [ ] Tenant `NativeConnector` credentials encrypted with Fernet (safe)
- [ ] All audit data in PostgreSQL (safe)

---

## 5. Logging

### 5.1 Application Logging
- [ ] Format: `%(asctime)s %(levelname)s %(name)s :: %(message)s`
- [ ] Logger name: `"jeeves"` for app-level logs
- [ ] Request logging middleware logs method, path, masked body for every request
- [ ] Sensitive fields redacted in logs: password, token, secret, key, authorization, etc.
- [ ] No f-strings in log messages — structured logging via `logger.info("action %s", entity_id)`
- [ ] AI calls logged with model name, token count, latency
- [ ] All worker activity logged with worker type and job ID

### 5.2 External Service Logging
- [ ] OpenAI API calls logged with WARNING on errors
- [ ] Webhook receipts logged with source, event type, tenant
- [ ] Webhook send failures logged with target URL and status
- [ ] Stripe/Shopify/Recharge API errors logged with WARNING
- [ ] Email send failures logged with channel and error

### 5.3 Log Aggregation (Railway)
- [ ] Railway Dashboard → Logs for real-time streaming
- [ ] Consider external log aggregation for production (e.g., Axiom, Better Stack, Datadog)
- [ ] Log retention policy defined (Railway retains recent logs; external service for longer)
- [ ] Structured JSON logs for external aggregator compatibility (optional enhancement)

### 5.4 Audit Logging
- [ ] Every workflow state transition logged to `TimelineEvent` and `WorkflowTransition`
- [ ] Every communication sent logged to `Communication`
- [ ] Every escalation logged to `Escalation`
- [ ] Every policy decision snapshotted in transition record
- [ ] Every admin action (policy change, resolve escalation) logged

---

## 6. Monitoring

### 6.1 Health Checks
- [ ] `GET /health` — basic alive check (returns `{"status": "ok"}`)
- [ ] `GET /health/ready` — readiness check (returns `{"status": "ok", "workers": {...}}`)
- [ ] `GET /health/db` — database connectivity check
- [ ] Railway health check configured to use `/health` endpoint
- [ ] Health check interval: 30 seconds, failure threshold: 3

### 6.2 Railway Metrics
- [ ] CPU usage monitored (alert if >80% sustained)
- [ ] Memory usage monitored (alert if >80% sustained)
- [ ] Disk usage monitored (alert if >80%)
- [ ] Network traffic monitored (spike detection)

### 6.3 Application Metrics (to implement)
- [ ] OpenAI API error rate and latency (per operation type)
- [ ] Webhook processing latency (event received → workflow created)
- [ ] Chat response latency (p50/p95/p99)
- [ ] Active workflow count per tenant
- [ ] Escalation rate (escalated / total workflows)
- [ ] Recovery rate (recovered / total payment failures)
- [ ] Stale/expired workflows per tenant
- [ ] Queue depth for each worker type

### 6.4 Alerts (to configure)
| Alert | Threshold | Action |
|-------|-----------|--------|
| OpenAI API errors | >5% in 5 min | Check API key, quota, OpenAI status |
| Health check failure | 3 consecutive failures | Railway auto-restart; investigate |
| Worker crash | Worker exits unexpectedly | Check logs, restart container |
| Escalation surge | >50% of active workflows escalated | Investigate policy or system issue |
| Redis unavailable | Connection refused | Fallback to in-memory (logged); alert |
| Database connection pool exhaustion | >80% of pool in use | Increase pool size or scale |
| Unhandled exceptions | Any in logs | Fix bug, deploy patch |
| SSL certificate expiry | <30 days remaining | Renew certificate |
| Persistent Volume disk space | >80% full | Clean Chroma orphans or resize volume |

### 6.5 Uptime Monitoring
- [ ] External uptime monitor configured (e.g., Pingdom, Better Stack, Uptime Robot)
- [ ] Monitors: public landing page, health endpoint, widget.js availability
- [ ] Alert on: downtime > 1 minute for production

---

## 7. CI/CD

### 7.1 GitHub Deployment (Railway Auto-Deploy)
- [ ] Railway connected to GitHub repo: `DavidSaatchyan/jeeves`
- [ ] Auto-deploy from `main` branch (production)
- [ ] Auto-deploy from `staging` branch (staging) — optional
- [ ] PR previews for feature branches — optional

### 7.2 Pre-Deploy Checks (to implement in CI)
- [ ] `python -c "from app.main import app"` — imports resolve
- [ ] `pytest api/tests/` — all tests pass (when tests exist)
- [ ] `ruff check` or `pyflakes` — no lint errors
- [ ] `alembic check` — migration is in sync with models
- [ ] `safety check` — no known vulnerable dependencies

### 7.3 Docker Build Checks
- [ ] Dockerfile builds successfully (`docker build -t jeeves .`)
- [ ] No `pip install` failures
- [ ] Build time < 5 minutes
- [ ] Image size < 500 MB (python:3.11-slim is ~120 MB base)
- [ ] `.dockerignore` exists to exclude `__pycache__/`, `.env`, `*.db`, `chroma_data/`

### 7.4 Deployment Workflow
```
Developer pushes to main
    │
    ▼
GitHub detects push → Railway webhook triggered
    │
    ▼
Railway builds Docker image (Dockerfile)
    │
    ▼
Railway starts new container(s) with latest env vars
    │
    ▼
Alembic migrations run automatically (on startup)
    │
    ▼
Health check passes → new deployment is live
    │
    ▼
Old container(s) terminated gracefully
```

### 7.5 Post-Deploy Verification
- [ ] `/health` returns 200
- [ ] `/health/db` returns `{"status": "ok"}`
- [ ] Admin login works
- [ ] Widget chat responds (test via `/widget/chat`)
- [ ] Knowledge base chat responds (test via `/knowledge/chat`)
- [ ] Verify Chroma volume is mounted and collections accessible
- [ ] Check logs for startup errors or migration warnings
- [ ] Test one workflow trigger (webhook simulation)

---

## 8. Rollback Strategy

### 8.1 Application Rollback (Railway)
- [ ] Railway Dashboard → Deployments → select previous successful deployment → Rollback
- [ ] Rollback time: ~30 seconds (container restart, no rebuild)
- [ ] Downtime during rollback: ~10-15 seconds (container swap)

### 8.2 Database Rollback
- [ ] **Schema rollback**: Alembic `downgrade` command available for each migration
  ```
  alembic downgrade -1
  ```
- [ ] **Data rollback**: Restore from Railway PostgreSQL backup
  ```
  Railway Dashboard → PostgreSQL → Backups → Restore
  ```
- [ ] Rollback procedure for migration failure:
  1. Roll back application to previous version
  2. Run `alembic downgrade <prev_revision>` to revert schema
  3. If data migration occurred, restore from backup

### 8.3 ChromaDB Rollback
- [ ] Chroma volume is tied to deployment — rolling back app does NOT roll back Chroma
- [ ] If Chroma schema changes are incompatible, restore from backup or re-index from knowledge files
- [ ] Mitigation: avoid Chroma schema changes; use additive changes only

### 8.4 Full Rollback Procedure
```
1. Application: Railway Dashboard → Deployments → Rollback to previous version
2. Database schema: alembic downgrade <prev_revision>
3. Verify: /health, /health/db, admin login, widget chat
4. If schema/data corruption: Railway PostgreSQL → Backups → Restore
5. If Chroma corruption: re-upload knowledge files or restore from volume backup
```

### 8.5 Emergency Rollback (git revert)
```
git revert HEAD --no-edit
git push origin main
# Railway auto-deploys the revert
```

### 8.6 Principles
- Never amend pushed commits — always revert or fix forward
- Feature flags for risky changes (disable agent, disable channel) via admin panel
- Database changes should be additive (new columns, new tables) — avoid destructive migrations
- Test rollback procedure in staging before production

---

## 9. Pre-Launch Final Checklist

### 9.1 Security
- [ ] All passwords use bcrypt (already configured in `auth.py`)
- [ ] JWT access tokens expire in 15 minutes
- [ ] JWT refresh tokens expire in 30 days
- [ ] API keys prefixed with `sk_` and hashed with SHA-256
- [ ] All credentials encrypted with Fernet at rest
- [ ] HSTS header set (`max-age=63072000; includeSubDomains`)
- [ ] X-Content-Type-Options: nosniff
- [ ] X-Frame-Options: DENY
- [ ] CORS restricted to known origins (except widget endpoints)
- [ ] Webhook signatures verified (HMAC-SHA256)
- [ ] Rate limiting active on auth and chat endpoints
- [ ] Content moderation on widget chat (OpenAI moderation + keyword filter)
- [ ] Origin validation on widget endpoints

### 9.2 Capacity & Limits
- [ ] OpenAI rate limits compatible with expected request volume
- [ ] Chroma volume has sufficient space for expected document count
- [ ] PostgreSQL connection pool sized for API + 4 worker containers
- [ ] Knowledge base storage quota enforced (50 MB/tenant)
- [ ] Widget rate limit: 20 messages/min per IP
- [ ] Auth register rate limit: 3/hour per IP
- [ ] Auth login rate limit: 5/min per IP

### 9.3 Billing (MVP)
- [ ] Trial period: 14 days from registration
- [ ] Trial limit: 100 dialogs per tenant
- [ ] Hard-coded "free" plan — no payment collection in MVP
- [ ] 402 Payment Required returned when limits exceeded
- [ ] Stripe billing integration planned but not yet implemented

### 9.4 Documentation
- [ ] README.md up to date
- [ ] DEPLOY.md up to date
- [ ] .env.example lists all required environment variables
- [ ] API documentation accessible at `/docs`

---

## 10. Post-Launch Monitoring (First 72 Hours)

### 10.1 First Hour
- [ ] Verify all health endpoints return 200
- [ ] Verify OpenAI API calls succeed (check logs for errors)
- [ ] Verify webhook receivers respond (POST test webhooks)
- [ ] Verify worker containers are running
- [ ] Test complete payment recovery flow end-to-end

### 10.2 First 24 Hours
- [ ] Monitor error rate in logs
- [ ] Monitor worker queue depths
- [ ] Monitor response latency
- [ ] Verify email delivery (SendGrid/Resend delivery events)
- [ ] Verify all registered tenants can log in
- [ ] Test knowledge base upload and search

### 10.3 First 72 Hours
- [ ] Review billing counters (dialogs_used, resolved_count)
- [ ] Check Chroma volume usage
- [ ] Review escalation rate
- [ ] Review recovery rate
- [ ] Adjust policies based on initial workflow outcomes
