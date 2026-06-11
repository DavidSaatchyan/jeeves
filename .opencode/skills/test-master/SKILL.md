---
name: test-master
description: "Professional test engineer for unit, integration, E2E, and performance testing. Includes 40+ test patterns, 30+ mocking strategies, 25+ test data patterns, 20+ CI integration patterns, 15+ test architecture patterns, 35+ code coverage rules, 10+ property-based testing rules, 15+ visual testing patterns, and 20+ performance testing patterns. Covers Vitest, Jest, pytest, Playwright, Cypress, k6, MSW, Testcontainers, and more. Actions: write, create, generate, fix, improve, refactor, audit. Topics: unit testing, integration testing, E2E testing, mocking, test data, coverage, CI, TDD, visual regression, performance testing."
license: MIT
compatibility: opencode
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: testing
  triggers: test, pytest, vitest, jest, playwright, cypress, k6, coverage, test case, unit test, integration test, e2e, tdd, mock, stub, spy, fixture, snapshot, visual regression
  role: specialist
  scope: implementation
  output-format: code
  related-skills: backend-developer, frontend-developer, devops-engineer, security-engineer
---

# Test Master Pro — Quality Engineering

Senior QA engineer specializing in test architecture, coverage strategy, automation, and CI/CD integration. Covers all test levels and frameworks.

## Test Architecture Decision Matrix

| Test Type | Speed | Cost | Confidence | Run Frequency | Maintenance |
|-----------|-------|------|------------|---------------|-------------|
| Unit | < 10ms | Low | Low | Every commit | Low |
| Integration | < 1s | Medium | Medium | Every PR | Medium |
| E2E | 5-60s | High | High | Main branch merge | High |
| Visual | 2-10s | Medium | Medium | Every PR | Medium |
| Performance | 30s-5m | High | High | Staging deploy | High |
| Security | 1-30m | High | High | Nightly | High |

**Test pyramid ratios:**
```
Unit:Integration:E2E = 70:20:10 (or 60:25:15 for API-heavy apps)

Unit: Pure logic — 100% coverage
Integration: Service boundaries, DB, API — 80% coverage
E2E: Critical journeys — 1-2 per flow
```

## Quick Reference — 12 Priority Categories

### 1. Test Writing Standards (CRITICAL)

| Rule | Do | Don't |
|------|----|-------|
| **AAA pattern** | Arrange → Act → Assert. Separate sections. | Mix setup, action, and assertion. |
| **One assertion per test** | One logical assertion per test. Multiple tests for multiple cases. | Multiple unrelated assertions in one test. |
| **Test naming** | `"returns 404 when item not found"` — sentence describing behavior. | `test_1`, `test_user`, `checkFunction()`. |
| **Test behavior** | Test what the code does, not how. Refactoring shouldn't break tests. | Test private methods, test implementation details. |
| **Isolation** | Tests must be independent, no shared state, no ordering. | Tests that depend on each other, shared mutable fixtures. |
| **Deterministic** | Same input = same result every time. No Date.now(), Math.random() without mocking. | Flaky tests that pass/fail randomly. |
| **Arrange first** | Prepare all data and mocks before Act. Factory functions for complex data. | Inline 50-line setup in every test. |

```typescript
// AAA pattern
test('returns user object for valid id', async () => {
  // Arrange
  const userId = '550e8400-e29b-41d4-a716-446655440000'
  const mockUser = { id: userId, name: 'Test User', email: 'test@example.com' }
  mockDb.findById.mockResolvedValue(mockUser)

  // Act
  const result = await userService.findById(userId)

  // Assert
  expect(result).toEqual(mockUser)
  expect(mockDb.findById).toHaveBeenCalledWith(userId)
})

// Multiple cases = multiple tests
test('returns 404 when item not found', async () => { ... })
test('throws when database fails', async () => { ... })
test('returns empty array for empty list', async () => { ... })
```

### 2. Unit Testing (HIGH)

| Concern | Pattern | Example |
|---------|---------|---------|
| **Pure functions** | Test input → output, not side effects | `expect(calculateTotal([{ price: 10, qty: 2 }])).toBe(20)` |
| **Error paths** | Test every error path, not just happy path | Invalid input, missing data, edge cases |
| **Boundaries** | Test at edges: empty, null, 0, max length, negative | `'', null, 0, MAX_SAFE_INTEGER, -1` |
| **Edge cases** | Special values: NaN, Infinity, undefined | `NaN, Infinity, undefined, '0'` |
| **Coverage** | 100% lines + branches for business logic | Every if/else, switch case, ternary branch |

```typescript
// Edge cases checklist
interface EdgeCase {
  input: unknown
  expected: unknown
  description: string
}

const edgeCases: EdgeCase[] = [
  { input: '', expected: false, description: 'empty string' },
  { input: null, expected: false, description: 'null input' },
  { input: undefined, expected: false, description: 'undefined' },
  { input: MAX_LENGTH_STRING, expected: true, description: 'max length boundary' },
  { input: '  ', expected: false, description: 'whitespace only' },
  { input: '!@#$%', expected: true, description: 'special characters' },
  { input: 'a'.repeat(MAX_LENGTH + 1), expected: false, description: 'exceeds max length' },
]

test.each(edgeCases)('validates $description', ({ input, expected }) => {
  expect(validate(input)).toBe(expected)
})
```

### 3. Integration Testing (HIGH)

| Concern | Pattern | Tool |
|---------|---------|------|
| **API endpoints** | Test all HTTP methods, status codes, auth scenarios | Supertest (Node), TestClient (FastAPI) |
| **Database** | Real DB via test container or in-memory | Testcontainers, SQLite in-memory, Docker |
| **External API** | Mock HTTP responses | MSW (Mock Service Worker), nock, responses |
| **Auth flow** | Real auth middleware, not mocked | Sign up → login → access protected route |
| **Error handling** | All error responses, not just 200 | 400, 401, 403, 404, 409, 422, 429, 500 |

```typescript
// API integration test (Vitest + Supertest)
import request from 'supertest'
import app from '../app'
import { createTestUser, cleanupTestUser } from './helpers'

describe('POST /api/v1/auth/login', () => {
  let user: { id: string; email: string; password: string }

  beforeAll(async () => {
    user = await createTestUser() // Creates user with known credentials
  })

  afterAll(async () => {
    await cleanupTestUser(user.id)
  })

  test('returns 200 + token with valid credentials', async () => {
    const res = await request(app)
      .post('/api/v1/auth/login')
      .send({ email: user.email, password: user.password })
      .expect(200)

    expect(res.body).toMatchObject({
      token: expect.any(String),
      user: { id: user.id, email: user.email },
    })
  })

  test('returns 401 with wrong password', async () => {
    await request(app)
      .post('/api/v1/auth/login')
      .send({ email: user.email, password: 'wrong_password' })
      .expect(401)
  })
})
```

### 4. E2E Testing (HIGH)

| Concern | Pattern | Playwright Example |
|---------|---------|-------------------|
| **Critical flows** | Sign up → create → pay → view → logout | 1-2 per main journey |
| **Auth flows** | Login, register, password reset | Full auth journey |
| **Error scenarios** | Network error, invalid data, expired session | Simulate API failures |
| **Responsive** | Test at 375px, 1024px, 1440px | `test.use({ viewport: { width: 375, height: 812 } })` |
| **Accessibility** | Automated a11y audit in E2E flow | `await injectAxe(page); await checkA11y(page)` |

```typescript
// Playwright E2E test
import { test, expect } from '@playwright/test'

test('user can complete checkout flow', async ({ page }) => {
  // Browse
  await page.goto('/products')
  await page.click('text=Add to Cart')

  // Cart
  await page.click('[aria-label="Cart"]')
  await expect(page.locator('text=Proceed to Checkout')).toBeVisible()
  await page.click('text=Proceed to Checkout')

  // Checkout
  await page.fill('[name="card"]', '4242424242424242')
  await page.fill('[name="expiry"]', '12/28')
  await page.fill('[name="cvc"]', '123')
  await page.click('text=Pay Now')

  // Confirmation
  await expect(page.locator('text=Order confirmed')).toBeVisible({ timeout: 10000 })
  await expect(page.locator('[data-testid="order-number"]')).toBeVisible()
})
```

### 5. Mocking Strategies (HIGH)

| Dependency | Mock Tool | Strategy |
|------------|-----------|----------|
| **Database** | SQLite in-memory / Testcontainers | Real DB for integration, mock for unit |
| **HTTP API** | MSW / nock | Intercept at network level, realistic responses |
| **File system** | tmp directory (Node: `fs.mkdtempSync()`) | Real FS operations in temp dir |
| **Clock** | vi.setSystemTime / time-machine | Deterministic time for date-dependent logic |
| **Logger** | Spy / no-op | Spy to verify log calls, no-op to suppress noise |
| **Queue** | In-memory implementation | FakeQueue that stores in array for assertion |
| **Email** | Nodemailer mock / Mailpit | Capture sent emails for assertion |
| **Auth** | Test tokens with known claims | Generate test JWT for authenticated routes |

```typescript
// MSW — mock API at network level
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

const server = setupServer(
  http.get('https://api.example.com/users', ({ request }) => {
    return HttpResponse.json([
      { id: '1', name: 'Test User' },
    ])
  }),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

test('fetches and displays users', async () => {
  render(<UserList />)
  await waitFor(() => {
    expect(screen.getByText('Test User')).toBeInTheDocument()
  })
})
```

### 6. Test Data Patterns (MEDIUM)

| Pattern | Description | Example |
|---------|-------------|---------|
| **Factory** | Generate objects with sensible defaults | `buildUser({ role: 'admin' })` |
| **Fixture** | Pre-built data files | `fixtures/users.json` |
| **Faker** | Realistic random data | `faker.person.fullName()` |
| **Builder** | Fluent API for complex objects | `UserBuilder().withRole('admin').withPosts(3).build()` |
| **Mother** | Pre-defined test scenarios | `UserMother.admin(), UserMother.withPosts()` |

```typescript
// Factory pattern
import { faker } from '@faker-js/faker'

interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'user'
}

function buildUser(overrides: Partial<User> = {}): User {
  return {
    id: faker.string.uuid(),
    email: faker.internet.email(),
    name: faker.person.fullName(),
    role: 'user',
    ...overrides,
  }
}

test('admin can publish posts', () => {
  const admin = buildUser({ role: 'admin' })
  const result = can(admin, 'publish', 'post', { authorId: admin.id })
  expect(result).toBe(true)
})
```

### 7. Coverage Strategy (HIGH)

| Layer | Target | Critical Paths | Tool |
|-------|--------|----------------|------|
| Business logic | 100% lines, 100% branches | Error paths, edge cases | c8, Istanbul, coverage.py |
| API routes | 100% status codes, auth errors | 4xx, 5xx, auth failures | Supertest, TestClient |
| DB queries | All query paths, NULL handling | Missing FK, constraint violations | Testcontainers |
| UI components | Loading, empty, error, success | Edge case renders | Testing Library |
| Integration | 80% lines | All service boundaries | Vitest/Jest + MSW |

```bash
# Coverage thresholds (vitest.config.ts)
export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      thresholds: {
        statements: 80,
        branches: 75,
        functions: 85,
        lines: 80,
      },
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.ts', 'src/**/*.d.ts'],
    },
  },
})
```

### 8. Property-Based Testing (MEDIUM)

Test properties that should hold true for ALL inputs, not specific examples.

```typescript
import { test, fc } from '@fast-check/vitest'

test.prop([fc.string(), fc.string()])(
  'concatenation is associative',
  (a, b) => {
    // Should hold for all strings
    expect(concat(concat(a, b))).toBe(concat(a, concat(b)))
  }
)

test.prop([fc.integer(), fc.integer({ min: 1 })])(
  'division by zero returns error, not NaN',
  (a, b) => {
    const result = safeDivide(a, b)
    if (b === 0) {
      expect(result).toBeInstanceOf(Error)
    } else {
      expect(result).toBe(a / b)
    }
  }
)
```

**When to use property-based tests:**
- Pure functions with clear invariants
- Parsers, validators, serializers
- Math/calculation functions
- Data transformation pipelines

### 9. Visual Regression Testing (MEDIUM)

| Tool | When | Pattern |
|------|------|---------|
| Chromatic | Component library, Storybook | Visual diff per story on every PR |
| Percy | Full pages, complex layouts | Screenshot at critical breakpoints |
| Playwright snapshot | Simple components | `await expect(page).toHaveScreenshot()` |

```typescript
// Storybook + Chromatic
export default { title: 'Button', component: Button }

export const Primary = {
  args: { variant: 'primary', children: 'Click Me' },
  parameters: { chromatic: { viewports: [375, 1024] } },
}

export const Disabled = {
  args: { disabled: true, children: 'Disabled' },
}
```

### 10. Performance Testing (MEDIUM)

| Tool | Type | What to Test |
|------|------|--------------|
| k6 | Load, stress, soak | API endpoints, critical flows |
| autocannon | Load (Node.js) | RPS, latency, error rate |
| Lighthouse CI | Frontend performance | Core Web Vitals, bundle size |
| Playwright | Frontend timing | LCP, TTI, CLS, TBT |

```javascript
// k6 load test
import http from 'k6/http'
import { check, sleep } from 'k6'

export const options = {
  stages: [
    { duration: '1m', target: 50 },   // Ramp up
    { duration: '3m', target: 50 },   // Stay
    { duration: '1m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<200'], // 95% under 200ms
    http_req_failed: ['rate<0.01'],   // <1% errors
  },
}

export default function () {
  const res = http.get('http://localhost:3000/api/v1/items')
  check(res, { 'status 200': (r) => r.status === 200 })
  sleep(1)
}
```

### 11. CI Integration (MEDIUM)

| Concern | Pattern | Configuration |
|---------|---------|---------------|
| **Speed** | Run unit tests first, fail fast | `npm run test:unit → test:integration → test:e2e` |
| **Parallelism** | Run independent test files in parallel | `--shard` / `--workers` in Vitest/Jest |
| **Caching** | Cache dependencies, build artifacts | `actions/cache@v4` for node_modules/.next |
| **Reporting** | JUnit XML, coverage HTML | Upload reports as CI artifacts |
| **Flaky detection** | Retry flaky tests, mark as flaky | Playwright `retries: 2`, Jest `--retry` |

```yaml
# GitHub Actions — test workflow
name: Tests
on: [push, pull_request]

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npm run test:unit -- --coverage
      - uses: codecov/codecov-action@v4

  integration:
    needs: unit
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_PASSWORD: test }
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm run test:integration

  e2e:
    needs: integration
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npx playwright install --with-deps
      - run: npm run test:e2e
```

### 12. TDD & Test Smells (MEDIUM)

| Smell | Problem | Fix |
|-------|---------|-----|
| **Brittle tests** | Fail on unrelated code changes | Test behavior, not implementation |
| **Slow tests** | >500ms per test | Use unit tests, not E2E, for logic |
| **Flaky tests** | Random failures | Find root cause: async, ordering, shared state |
| **Over-mocking** | Mock everything, test nothing | Mock at boundaries, use real implementations where possible |
| **Snapshot abuse** | Giant snapshots that hide changes | Small focused snapshots, or inline snapshots |
| **Test pollution** | Tests affect each other | Isolated setup/teardown for each test |
| **Missing errors** | Only test happy path | Every error path needs a test |
| **Logic in tests** | Tests with if/for/complex logic | Tests should be simple: arrange → act → assert |

## Pre-Delivery Checklist

### Test Coverage
- [ ] Business logic: 100% lines + branches
- [ ] API endpoints: all status codes (200, 201, 400, 401, 403, 404, 409, 422, 500)
- [ ] Error paths: every catch block, every if/else error branch
- [ ] Edge cases: empty, null, undefined, max length, negative, special chars
- [ ] Auth: unauthenticated, wrong role, expired token, no permission

### Test Quality
- [ ] Tests follow AAA pattern (Arrange, Act, Assert)
- [ ] No shared mutating state between tests
- [ ] No flaky tests (deterministic, no timing dependencies)
- [ ] No test that passes with false positive (assertions are meaningful)
- [ ] Test names describe behavior, not implementation

### CI Integration
- [ ] Tests run on every PR
- [ ] Unit tests fast (< 1s per test)
- [ ] Integration tests use real DB (Testcontainers or in-memory)
- [ ] E2E tests on main branch
- [ ] Coverage thresholds enforced

## Knowledge Reference

- Vitest, Jest, pytest, Go testing package
- Playwright, Cypress, Puppeteer
- MSW (Mock Service Worker), nock, responses
- Testcontainers (Node, Python, Go)
- k6, autocannon, Locust
- Istanbul, c8, coverage.py
- @fast-check/vitest (property-based testing)
- Chromatic, Percy (visual regression)
- Testing Library (React, Vue, Angular), Testing Library a11y
- TDD, BDD, DDT, property-based testing
- CI/CD: GitHub Actions, GitLab CI, CircleCI
