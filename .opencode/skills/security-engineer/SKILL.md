---
name: security-engineer
description: "Professional application security engineer. Includes OWASP Top 10 (2021) deep coverage, 40+ authentication/authorization patterns, 30+ cryptographic patterns, 20+ network security rules, 25+ API security patterns, 15+ dependency security rules, 20+ cloud security patterns, 10+ container security rules, 20+ secrets management patterns, and 10+ incident response templates. Covers Auth0, Supabase Auth, OAuth 2.0/OIDC, SAML, FIDO2/WebAuthn, bcrypt, argon2id, HashiCorp Vault, AWS KMS, and more. Actions: audit, review, fix, implement, harden, test. Topics: authentication, authorization, encryption, injection prevention, secret management, network security, compliance."
license: MIT
compatibility: opencode
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: security
  triggers: security, auth, OWASP, vulnerability, CVE, encryption, JWT, injection, XSS, CSRF, SSRF, rate limit, CORS, CSP, HSTS, OAuth, SAML, FIDO2, WebAuthn, password, hash, bcrypt, argon2, secret, vault, compliance, GDPR, SOC2, PCI, audit
  role: specialist
  scope: implementation + audit
  output-format: code + document
  related-skills: backend-developer, devops-engineer, architecture-designer, test-master, frontend-developer
---

# Security Engineer Pro — Application Security

Security specialist covering OWASP Top 10, authentication, authorization, cryptography, network security, secrets management, and compliance. Defines secure-by-default patterns for all application layers.

## Quick Reference — 10 Priority Categories

### 1. OWASP Top 10 (2021) — CRITICAL

| # | Vulnerability | Risk | Prevention |
|---|--------------|------|------------|
| A01 | **Broken Access Control** | Users access unauthorized data | Verify ownership + role on every request. Deny by default. Test with different roles. |
| A02 | **Cryptographic Failures** | Data exposure, weak crypto | No custom crypto. TLS 1.3 everywhere. Encrypt secrets at rest. |
| A03 | **Injection** | SQL, NoSQL, OS command injection | Parameterized queries. Input validation (allowlist). Output encoding. ORM safety. |
| A04 | **Insecure Design** | Architecture-level vulnerabilities | Threat modeling. Security requirements in design. Rate limiting. |
| A05 | **Security Misconfiguration** | Default credentials, debug enabled | Minimal attack surface. Disable debug in production. Automated config scanning. |
| A06 | **Vulnerable Components** | Known CVEs in dependencies | Regular `npm audit`/`pip audit`. Dependabot/Snyk. SBOM generation. |
| A07 | **Auth Failures** | Brute force, credential stuffing | MFA. Account lockout. Rate limiter. Secure session management. Passwordless options. |
| A08 | **Data Integrity Failures** | Tampered data, deserialization attacks | Signature verification. CSP. SRI for CDN. Signed JWTs. |
| A09 | **Security Logging & Monitoring** | Undetected breaches | Structured audit logs. Alert on anomalies. SIEM integration. |
| A10 | **SSRF** | Access internal services | Allowlist outbound destinations. Validate URLs. Block private IP ranges. |

**OWASP testing checklist:**
```
[ ] A01 — Can user A access user B's data? Change role/ID in request, test.
[ ] A02 — TLS enabled? Weak ciphers disabled? Static assets encrypted?
[ ] A03 — SQL injection in all params? NoSQL injection? Command injection in uploads?
[ ] A04 — Rate limits on auth? Input limits? Secure defaults?
[ ] A05 — Debug endpoints disabled? Cors wildcard? Default credentials?
[ ] A06 — npm audit clean? Known CVEs? Outdated packages?
[ ] A07 — MFA available? Lockout after 5 attempts? Session timeout?
[ ] A08 — JWT signature verified? CSP headers set? SRI on CDN assets?
[ ] A09 — Auth events logged? Anomaly detection? Log retention?
[ ] A10 — Outbound URL allowlist? Private IP blocked? Redirect validation?
```

### 2. Authentication (CRITICAL)

| Concern | Standard | Implementation |
|---------|----------|----------------|
| **Password hashing** | bcrypt (cost ≥ 12) or argon2id | `await bcrypt.hash(password, 12)` |
| **JWT** | Access 15min, Refresh 7d with rotation | `expiresIn: '15m'`, rotate refresh on use |
| **Session** | Server-side in Redis, random session ID | `sess_` prefix, 24h expiry, extend on activity |
| **MFA** | TOTP (RFC 6238) or SMS backup | Required for admin panel, optional for users |
| **OAuth 2.0** | Authorization Code + PKCE | Never Implicit Grant. PKCE for SPA/mobile. |
| **OIDC** | OpenID Connect on top of OAuth 2.0 | `id_token` for user info, `access_token` for API |
| **WebAuthn** | FIDO2/Passkeys | Biometric + hardware key, phishing-resistant |
| **Magic link** | Signed token in email | One-time use, 15min expiry, no password needed |
| **API keys** | Hash stored (sha256), prefix `sk_` | Rate limit 100/min, auto-rotate on leak |

```typescript
// Password hashing
import bcrypt from 'bcrypt'

const SALT_ROUNDS = 12

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, SALT_ROUNDS)
}

export async function verifyPassword(password: string, hash: string): Promise<boolean> {
  return bcrypt.compare(password, hash)
}

// JWT with rotation
import jwt from 'jsonwebtoken'

interface TokenPayload {
  sub: string       // user ID
  role: string      // user role
  type: 'access' | 'refresh'
}

export function signAccessToken(userId: string, role: string): string {
  return jwt.sign({ sub: userId, role, type: 'access' }, ACCESS_SECRET, {
    algorithm: 'HS256',
    expiresIn: '15m',
    issuer: APP_NAME,
  })
}

export function signRefreshToken(userId: string): string {
  return jwt.sign({ sub: userId, type: 'refresh', jti: crypto.randomUUID() }, REFRESH_SECRET, {
    algorithm: 'HS256',
    expiresIn: '7d',
    issuer: APP_NAME,
  })
}
```

### 3. Authorization (CRITICAL)

| Pattern | When | Implementation |
|---------|------|----------------|
| **RBAC** | Simple role hierarchy | `user.role === 'admin'` middleware |
| **ABAC** | Complex attribute-based rules | Policy engine: `can(user, 'edit', document)` |
| **Ownership check** | User can only access own data | `document.userId === req.user.id` |
| **Tenant isolation** | Multi-tenant apps | `WHERE tenant_id = $1` on every query |
| **Row-level security** | PostgreSQL RLS | `CREATE POLICY user_isolation ON documents FOR ALL USING (user_id = current_user_id())` |

```typescript
// ABAC policy engine
type Action = 'create' | 'read' | 'update' | 'delete' | 'publish'
type Resource = 'post' | 'comment' | 'user' | 'settings'

const policies: Record<string, (user: User, resource: unknown) => boolean> = {
  'post:publish': (user, post: Post) =>
    user.role === 'admin' || (user.role === 'editor' && post.authorId === user.id),
  'user:delete': (user, target: User) =>
    user.role === 'admin' || user.id === target.id,
}

export function can(user: User, action: Action, resource: Resource, target: unknown): boolean {
  const key = `${resource}:${action}`
  const policy = policies[key]
  if (!policy) return false
  return policy(user, target)
}
```

### 4. Input Validation & Injection Prevention (HIGH)

| Attack | Prevention | Implementation |
|--------|------------|----------------|
| **SQL injection** | Parameterized queries | `SELECT * FROM users WHERE id = $1` — never `WHERE id = '${id}'` |
| **NoSQL injection** | Schema validation + type checking | `z.object({ id: z.string().uuid() })` |
| **XSS** | Output encoding + CSP | React auto-escapes. `dangerouslySetInnerHTML` = last resort |
| **Command injection** | No shell execution with user input | `exec('ls ' + input)` — NEVER. Use `execFile` with args array. |
| **Path traversal** | Validate + normalize paths | `path.resolve(base, userPath).startsWith(base)` |
| **LDAP injection** | Escape special chars | Use parameterized LDAP queries |
| **XPath injection** | Parameterize | No user input in XPath expressions |

```typescript
// Input validation with allowlist
import { z } from 'zod'

const userInputSchema = z.object({
  email: z.string().email().max(255),
  name: z.string().min(2).max(100).regex(/^[a-zA-Z\s]+$/),
  age: z.number().int().min(18).max(150),
  role: z.enum(['admin', 'user']).default('user'),
})

// Path traversal prevention
import path from 'path'
import fs from 'fs'

function safeReadFile(baseDir: string, userPath: string): Buffer {
  const fullPath = path.resolve(baseDir, userPath)
  if (!fullPath.startsWith(baseDir)) {
    throw new Error('Path traversal detected')
  }
  return fs.readFileSync(fullPath)
}
```

### 5. Cryptography (HIGH)

| Concern | Standard | Do | Don't |
|---------|----------|----|-------|
| **Hashing (passwords)** | bcrypt (cost ≥ 12) or argon2id | Use for password storage | SHA-256, MD5 (fast, no salt suitable) |
| **Hashing (integrity)** | SHA-256 / SHA-3 | File integrity, signatures | MD5, SHA-1 (collision vulnerable) |
| **Symmetric encryption** | AES-256-GCM | Encrypt data at rest | AES-ECB, DES, RC4 |
| **Asymmetric** | RSA-4096 or ECDSA P-384 | Key exchange, signatures | RSA < 2048, DSA |
| **TLS** | TLS 1.3 | All traffic in transit | TLS < 1.2, SSL any version |
| **Key generation** | crypto.randomBytes / Web Crypto API | API keys, session tokens | Math.random(), Date.now() |
| **JWT algorithm** | HS256 or RS256 | Token signing | `alg: 'none'`, `alg: 'HS256'` with public key |

```typescript
// AES-256-GCM encryption
import crypto from 'crypto'

const ALGORITHM = 'aes-256-gcm'
const IV_LENGTH = 16
const TAG_LENGTH = 16

export function encrypt(text: string, key: Buffer): string {
  const iv = crypto.randomBytes(IV_LENGTH)
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv)
  let encrypted = cipher.update(text, 'utf8', 'hex')
  encrypted += cipher.final('hex')
  const tag = cipher.getAuthTag().toString('hex')
  return `${iv.toString('hex')}:${tag}:${encrypted}`
}

export function decrypt(encoded: string, key: Buffer): string {
  const [ivHex, tagHex, encrypted] = encoded.split(':')
  const iv = Buffer.from(ivHex, 'hex')
  const tag = Buffer.from(tagHex, 'hex')
  const decipher = crypto.createDecipheriv(ALGORITHM, key, iv)
  decipher.setAuthTag(tag)
  let decrypted = decipher.update(encrypted, 'hex', 'utf8')
  decrypted += decipher.final('utf8')
  return decrypted
}
```

### 6. Network & API Security (HIGH)

| Concern | Implementation | Example |
|---------|----------------|---------|
| **CORS** | Allowlist specific origins | `origin: ['https://app.example.com']` — not `*` |
| **CSP** | Content Security Policy headers | `script-src 'self'; object-src 'none'` |
| **HSTS** | Strict Transport Security | `max-age=31536000; includeSubDomains; preload` |
| **Rate limiting** | Per-IP, per-user, per-endpoint | Auth: 10/min, API: 1000/min, upload: 10/min |
| **CORS preflight** | Handle OPTIONS correctly | Return 204 with correct headers |
| **HTTPS redirect** | Redirect all HTTP to HTTPS | 301 redirect, HSTS preload |
| **Security headers** | helmet (Node) or similar | X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy: strict-origin |

```typescript
// Full security headers (Express with helmet)
import helmet from 'helmet'

app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", "data:", "https:"],
      connectSrc: ["'self'"],
      fontSrc: ["'self'", "https://fonts.gstatic.com"],
      objectSrc: ["'none'"],
      frameAncestors: ["'none'"],
    },
  },
  hsts: {
    maxAge: 31536000,
    includeSubDomains: true,
    preload: true,
  },
  referrerPolicy: { policy: 'strict-origin-when-cross-origin' },
}))

// Rate limiting
import rateLimit from 'express-rate-limit'

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 10,                    // 10 attempts
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'TOO_MANY_ATTEMPTS', message: 'Please try again later' },
})

app.use('/api/auth', authLimiter)
```

### 7. Secrets Management (HIGH)

| Rule | Do | Don't |
|------|----|-------|
| **Storage** | Environment variables or secret manager | Hardcode in source code |
| **Rotation** | Auto-rotate keys every 90 days | Use same key for years |
| **Access** | Least-privilege: app needs its own creds | Share service account across apps |
| **Audit** | Log every secret access and change | No audit trail |
| **Encryption** | Encrypt at rest (Vault/AWS KMS) | Plaintext secrets in config files |

```typescript
// Secret manager pattern (Vault)
import vault from 'node-vault'

const client = vault({ endpoint: process.env.VAULT_ADDR, token: process.env.VAULT_TOKEN })

export async function getSecret(path: string): Promise<Record<string, string>> {
  const { data } = await client.read(`secret/data/${path}`)
  return data.data
}

// Usage: secrets NEVER in code
const dbPassword = await getSecret('database/production').then(s => s.password)
```

### 8. Dependency Security (MEDIUM)

| Action | Frequency | Tool |
|--------|-----------|------|
| **Audit known CVE** | Every PR | `npm audit --audit-level=high` |
| **SCA scanning** | Daily | Dependabot, Snyk, GitHub Advanced Security |
| **Lock file check** | Every PR | Verify lock file matches package.json |
| **SBOM generation** | Every release | `cyclonedx-bom` or `spdx-sbom-generator` |
| **Outdated check** | Weekly | `npm outdated`, `pip list --outdated` |
| **Supply chain** | Evaluate new dependencies | Check: stars, maintenance, security history, license |

```bash
# npm audit with fail on critical
npm audit --audit-level=critical
if [ $? -ne 0 ]; then
  echo "Critical vulnerabilities found! Fix before merging."
  exit 1
fi

# SBOM generation
npx @cyclonedx/cyclonedx-npm --output-file bom.json
```

### 9. Container & Cloud Security (MEDIUM)

| Concern | Pattern | Implementation |
|---------|---------|----------------|
| **Docker** | Non-root user, minimal base | `FROM node:20-alpine`, `USER node` |
| **Image scanning** | Scan for CVEs in base image | `docker scan`, Trivy, Snyk |
| **IAM** | Least-privilege roles | Per-service IAM roles, no admin service accounts |
| **Network** | Private subnets for DB/cache | No public DB access, security groups |
| **WAF** | Web Application Firewall | AWS WAF, Cloudflare WAF |
| **DDoS** | Rate limiting + CDN + auto-scaling | Cloudflare, AWS Shield |
| **K8s security** | Pod security policies, network policies | No privileged containers, RBAC for API |

```dockerfile
# Secure Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
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
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:3000/health || exit 1
CMD ["node", "dist/index.js"]
```

### 10. Logging & Incident Response (MEDIUM)

| Concern | Implementation |
|---------|----------------|
| **Audit log** | Log: login (success/failure), access denial, privilege change, data export, config change |
| **Log format** | Structured JSON: `{ timestamp, level, message, userId, action, resource, ip, userAgent }` |
| **Retention** | 30d hot, 1y warm, 7y cold (compliance-dependent) |
| **Alerting** | Alert on: unusual login patterns, mass data access, privilege escalation, failed admin login |
| **Incident response** | Triage → contain → eradicate → recover → postmortem |

```typescript
// Security audit logger
interface AuditEvent {
  userId: string
  action: 'login' | 'login_failed' | 'logout' | 'access_denied' | 'create' | 'update' | 'delete' |
          'export' | 'privilege_change' | 'config_change'
  resource: string
  resourceId?: string
  details?: unknown
  ip: string
  userAgent: string
}

function auditLog(event: AuditEvent): void {
  logger.info({
    type: 'audit',
    timestamp: new Date().toISOString(),
    ...event,
  })
}

// Usage
auditLog({
  userId: req.user.id,
  action: 'access_denied',
  resource: 'admin_panel',
  ip: req.ip,
  userAgent: req.headers['user-agent'] || 'unknown',
})
```

## Pre-Audit Checklist

### Authentication
- [ ] Passwords hashed with bcrypt (cost ≥ 12) or argon2id
- [ ] JWT secrets strong, algorithm validated as HS256/RS256
- [ ] MFA available for admin access
- [ ] Account lockout after 5 failed attempts
- [ ] Session timeout (15-30min idle, 24h absolute)
- [ ] Passwordless options (magic link, WebAuthn)

### Authorization
- [ ] Ownership check on every data mutation
- [ ] RBAC/ABAC enforced at middleware, not just frontend
- [ ] Deny by default (allowlist approach)
- [ ] No IDOR vulnerabilities (test with different user IDs)
- [ ] Rate limiting on sensitive endpoints

### Data Protection
- [ ] All traffic over TLS 1.3
- [ ] Secrets in env vars / secret manager, never in code
- [ ] PII encrypted at rest
- [ ] Input validation on every endpoint (allowlist)
- [ ] Parameterized queries throughout

### Infrastructure
- [ ] Security headers set (CSP, HSTS, X-Frame-Options)
- [ ] CORS allowlist (not wildcard)
- [ ] Container runs as non-root
- [ ] Dependencies scanned for CVEs
- [ ] Debug mode disabled in production

## Knowledge Reference

- OWASP Top 10 (2021), OWASP ASVS (Application Security Verification Standard)
- OAuth 2.0 (RFC 6749), OIDC (RFC 7519), JWT (RFC 7519), WebAuthn (FIDO2)
- bcrypt, argon2id, AES-256-GCM, SHA-256/3, RSA-4096, ECDSA P-384
- HashiCorp Vault, AWS KMS / Secrets Manager, Azure Key Vault, GCP Secret Manager
- Docker security, Kubernetes security, AWS IAM / Azure RBAC / GCP IAM
- CSP, HSTS, CORS, SRI, HPKP
- OWASP ZAP, Burp Suite, Semgrep, SonarQube, Snyk, Dependabot
- SOC 2, PCI DSS, GDPR, HIPAA, ISO 27001
- NIST Cybersecurity Framework, MITRE ATT&CK
