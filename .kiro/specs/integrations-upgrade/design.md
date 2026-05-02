# Design: Integrations Upgrade

## Overview

This feature expands Jeeves's integration surface from a single custom-REST + HubSpot OAuth model into a full multi-connector platform. The goal is to let tenants connect Shopify, WooCommerce, and Stripe stores out of the box, configure incoming/outgoing webhooks for real-time context injection and event notifications, control how customers are identified across all connectors, and automatically write conversation summaries back to their CRM or webhook endpoint.

All new connectors follow the same pattern: credentials are encrypted at rest with Fernet symmetric encryption, external calls are capped at 10 s, and AgentTool rows are auto-provisioned on connect so the agent can immediately use the new capabilities without manual configuration.

### Design Goals

- Zero-config agent tools: connecting a provider auto-creates the relevant AgentTool rows.
- Uniform credential security: all secrets encrypted with Fernet before DB storage.
- Async side-effects: webhooks and write-back run in Celery, never blocking the chat response.
- Idempotent mutations: Stripe and Shopify write operations carry idempotency keys.
- Extensible connector registry: adding a new provider requires only a new module + connector record.

---

## Architecture

```mermaid
graph TD
    subgraph API
        A[agent.py] -->|dispatch_tool| B[routes_tools.py]
        A -->|read_customer| C[crm.py]
        C --> D[hubspot.py]
        C --> E[connectors/shopify.py]
        C --> F[connectors/woocommerce.py]
        C --> G[connectors/stripe_connector.py]
        H[routes_integrations.py] -->|CRUD| I[(PostgreSQL)]
        H -->|encrypt/decrypt| J[crypto.py]
    end

    subgraph Worker
        K[tasks.py] -->|writeback_conversation| L[LLM summary]
        L -->|HubSpot note| D
        L -->|POST| M[Tenant webhook]
        K -->|send_outgoing_webhook| M
    end

    subgraph Widget
        N[widget.js] -->|identify + extra_fields| O[/widget/chat]
    end

    O --> A
    A -->|conversation.started| K
    A -->|conversation.ended| K
    A -->|action.called| K
```

### Key Architectural Decisions

**Connector abstraction**: Each provider lives in `connectors/<provider>.py` and exposes a typed async interface. `crm.py` is extended to delegate to native connectors when `NativeConnector` rows exist, keeping `agent.py` unchanged.

**Credential encryption**: A single `crypto.py` module wraps `cryptography.fernet`. All connector modules call `crypto.encrypt()` before writing and `crypto.decrypt()` before using credentials. The Fernet key is loaded from `settings.fernet_key` (env var `FERNET_KEY`).

**Auto-provisioned tools**: `connectors/registry.py` defines the canonical AgentTool specs per provider. `routes_integrations.py` calls `registry.provision_tools(db, tenant_id, provider)` on connect and `registry.deprovision_tools(db, tenant_id, provider)` on disconnect.

**Webhook delivery**: Outgoing webhooks are dispatched via a Celery task `send_outgoing_webhook` with a 3-retry exponential backoff. Incoming webhook calls happen synchronously at conversation start (best-effort, timeout 5 s so as not to block the user).

---

## Components and Interfaces

### `api/app/crypto.py`

```python
def encrypt(plaintext: str) -> str: ...   # Fernet encrypt → base64 str
def decrypt(ciphertext: str) -> str: ...  # Fernet decrypt → plaintext str
```

### `api/app/connectors/shopify.py`

```python
async def get_orders_by_email(credentials: dict, email: str) -> list[dict]: ...
async def get_order(credentials: dict, order_id: str) -> dict: ...
async def update_shipping_address(
    credentials: dict, order_id: str, address: dict, idempotency_key: str
) -> dict: ...
async def cancel_order(
    credentials: dict, order_id: str, idempotency_key: str
) -> dict: ...
```

Credentials dict: `{"shop": "mystore.myshopify.com", "access_token": "<decrypted>"}`.
All calls use `httpx.AsyncClient(timeout=10.0)` against `https://{shop}/admin/api/2024-01/`.

### `api/app/connectors/woocommerce.py`

```python
async def get_orders_by_email(credentials: dict, email: str) -> list[dict]: ...
async def get_order(credentials: dict, order_id: str) -> dict: ...
async def update_order_status(credentials: dict, order_id: str, status: str) -> dict: ...
async def get_customer(credentials: dict, email: str) -> dict: ...
```

Credentials dict: `{"base_url": "https://mystore.com", "consumer_key": "...", "consumer_secret": "..."}`.
Uses WooCommerce REST API v3 with HTTP Basic auth.

### `api/app/connectors/stripe_connector.py`

```python
async def get_subscription(credentials: dict, customer_email: str) -> dict: ...
async def get_next_invoice(credentials: dict, customer_email: str) -> dict: ...
async def cancel_at_period_end(
    credentials: dict, subscription_id: str, idempotency_key: str
) -> dict: ...
```

Credentials dict: `{"secret_key": "<decrypted>"}`.
Uses `stripe` Python SDK with `stripe.api_key` set per-call. `cancel_at_period_end` passes `idempotency_key` as `stripe.Subscription.modify(..., idempotency_key=idempotency_key)`.

### `api/app/connectors/registry.py`

```python
TOOL_SPECS: dict[str, list[dict]] = {
    "shopify": [...],      # list of AgentToolIn-compatible dicts
    "woocommerce": [...],
    "stripe": [...],
}

def provision_tools(db: Session, tenant_id: UUID, provider: str) -> list[AgentTool]: ...
def deprovision_tools(db: Session, tenant_id: UUID, provider: str) -> None: ...
```

### `api/app/routes_integrations.py`

New FastAPI router at `/integrations`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/integrations` | List all connectors + status for tenant |
| POST | `/integrations/native` | Create/update NativeConnector (encrypts credentials) |
| DELETE | `/integrations/native/{provider}` | Disconnect + deprovision tools |
| POST | `/integrations/native/{provider}/test` | Test connector connectivity |
| GET | `/integrations/webhook` | Get WebhookConfig |
| POST | `/integrations/webhook` | Create/update WebhookConfig |
| GET | `/integrations/writeback` | Get WriteBackConfig |
| POST | `/integrations/writeback` | Create/update WriteBackConfig |

### `api/app/routes_chat.py` (extension)

After agent.run() completes, fire Celery tasks:
- `send_outgoing_webhook.delay(...)` for `conversation.started` / `conversation.ended` / `action.called`
- `writeback_conversation.delay(...)` on `conversation.ended`

### `frontend/widget.js` (extension)

`JeevesWidget.identify()` extended to accept arbitrary extra fields:

```js
JeevesWidget.identify({ user_id: "u@example.com", order_id: "1234", plan: "pro" })
```

Extra fields are merged into the `/widget/chat` POST body as `extra_fields: {...}`. The agent receives them in the system prompt context.

### `worker/tasks.py` (extension)

New Celery tasks:

```python
@app.task(name="tasks.send_outgoing_webhook")
def send_outgoing_webhook(tenant_id: str, event: str, payload: dict) -> dict: ...

@app.task(name="tasks.writeback_conversation")
def writeback_conversation(tenant_id: str, session_id: str) -> dict: ...
```

---

## Data Models

### `NativeConnector` (new table: `native_connectors`)

```python
class NativeConnector(Base):
    __tablename__ = "native_connectors"

    id          = Column(UUID, primary_key=True, default=_uuid)
    tenant_id   = Column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider    = Column(String(32), nullable=False)   # shopify | woocommerce | stripe
    status      = Column(String(16), default="connected", nullable=False)  # connected | disconnected | error
    credentials = Column(Text, nullable=False)          # Fernet-encrypted JSON string
    meta        = Column(JSONB, default=dict)            # shop domain, account name, etc.
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "provider"),)
```

Credentials are stored as `crypto.encrypt(json.dumps(raw_creds))`. Decryption happens only inside connector modules, never in route handlers.

### `WebhookConfig` (new table: `webhook_configs`)

```python
class WebhookConfig(Base):
    __tablename__ = "webhook_configs"

    tenant_id        = Column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    # Incoming: Jeeves calls this URL at conversation start to fetch context
    incoming_url     = Column(Text)
    incoming_secret  = Column(Text)   # HMAC-SHA256 signing secret (Fernet-encrypted)
    # Outgoing: Jeeves POSTs events here
    outgoing_url     = Column(Text)
    outgoing_secret  = Column(Text)   # Fernet-encrypted
    field_mapping    = Column(JSONB, default=dict)   # maps response fields → agent context keys
    events           = Column(JSONB, default=list)   # ["conversation.started","conversation.ended","action.called"]
    enabled          = Column(Boolean, default=True, nullable=False)
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at       = Column(DateTime, default=datetime.utcnow, nullable=False)
```

Incoming webhook flow: at conversation start, `agent.py` calls `fetch_incoming_webhook_context(db, tenant_id, user_id, extra_fields)` which POSTs to `incoming_url` with a signed payload and merges the response into the system prompt context.

Outgoing webhook payload shape:
```json
{
  "event": "conversation.ended",
  "tenant_id": "...",
  "user_id": "...",
  "session_id": "...",
  "timestamp": "2024-01-01T00:00:00Z",
  "data": { ... }
}
```

HMAC-SHA256 signature sent as `X-Jeeves-Signature: sha256=<hex>` header.

### `WriteBackConfig` (new table: `writeback_configs`)

```python
class WriteBackConfig(Base):
    __tablename__ = "writeback_configs"

    tenant_id                  = Column(UUID, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    type                       = Column(String(32), default="off", nullable=False)  # off | hubspot_note | webhook
    hubspot_note_enabled       = Column(Boolean, default=False, nullable=False)
    hubspot_task_on_escalation = Column(Boolean, default=False, nullable=False)
    webhook_url                = Column(Text)
    created_at                 = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at                 = Column(DateTime, default=datetime.utcnow, nullable=False)
```

### `CRMConfig` extension

Add `primary_identifier` column to existing `crm_config` table:

```python
primary_identifier = Column(String(32), default="email", nullable=False)
# Values: "email" | "user_id" | "custom"
# When "custom", the identifier field name is stored in capabilities["identifier_field"]
```

### `ChatLog` extension

Add `session_id` and `extra_fields` columns:

```python
session_id   = Column(UUID, index=True)   # groups turns of one conversation
extra_fields = Column(JSONB, default=dict) # from widget.identify() extra fields
```

### Migration summary

| Table | Change |
|-------|--------|
| `native_connectors` | New table |
| `webhook_configs` | New table |
| `writeback_configs` | New table |
| `crm_config` | Add `primary_identifier VARCHAR(32) DEFAULT 'email'` |
| `chat_logs` | Add `session_id UUID`, `extra_fields JSONB` |


---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Credential encryption round-trip

*For any* connector credentials dict (Shopify, WooCommerce, or Stripe), encrypting the JSON-serialized credentials and then decrypting the result must produce a value equal to the original plaintext, and the encrypted ciphertext must not equal the plaintext.

**Validates: Requirements 1.1, 3.2, 7.1 (Fernet encrypt/decrypt correctness and security)**

### Property 2: Connector order lookup by email

*For any* configured native connector (Shopify or WooCommerce) and any customer email, calling `get_orders_by_email` with that email must return only orders associated with that email address (no cross-customer data leakage).

**Validates: Requirements 1.3, 2.2**

### Property 3: Write operations carry idempotency keys

*For any* mutating connector call that accepts an `idempotency_key` parameter (Shopify `update_shipping_address`, Shopify `cancel_order`, Stripe `cancel_at_period_end`), the key must appear verbatim in the outgoing HTTP request (header or SDK parameter), and calling the operation twice with the same key must not produce a different observable side-effect.

**Validates: Requirements 1.4, 1.5, 3.1**

### Property 4: Tool auto-provisioning on connect

*For any* supported provider (`shopify`, `woocommerce`, `stripe`), calling `registry.provision_tools(db, tenant_id, provider)` must create AgentTool rows whose names exactly match the canonical tool spec for that provider, and all created tools must be enabled.

**Validates: Requirement 1.6**

### Property 5: Tool deprovisioning round-trip

*For any* tenant and provider, provisioning tools and then deprovisioning them must leave zero AgentTool rows for that provider under that tenant.

**Validates: Requirement 1.7**

### Property 6: WooCommerce connector uses v3 REST with Basic auth

*For any* WooCommerce connector call, the outgoing HTTP request URL must contain `/wp-json/wc/v3/` and the `Authorization` header must be a valid HTTP Basic auth value derived from the configured `consumer_key` and `consumer_secret`.

**Validates: Requirement 2.1**

### Property 7: Incoming webhook context injected at conversation start

*For any* tenant with a `WebhookConfig` that has a non-null `incoming_url` and `enabled=true`, starting a conversation must result in an HTTP POST to `incoming_url` before the agent's first LLM call, and the response fields (mapped via `field_mapping`) must appear in the system prompt context.

**Validates: Requirement 4.1**

### Property 8: Outgoing webhook and write-back are enqueued asynchronously

*For any* conversation event (`conversation.started`, `conversation.ended`, `action.called`) where the tenant has a matching `WebhookConfig.events` entry, a Celery task must be enqueued (`.delay()` called) rather than executed inline in the request handler. Similarly, `writeback_conversation` must be enqueued, not called synchronously.

**Validates: Requirements 4.2, 6.3**

### Property 9: Outgoing webhook payload is HMAC-SHA256 signed

*For any* outgoing webhook payload, the HTTP request must include an `X-Jeeves-Signature` header of the form `sha256=<hex>` where the hex value is the HMAC-SHA256 of the raw JSON body using the tenant's `outgoing_secret`.

**Validates: Requirement 4.3**

### Property 10: All configured events trigger outgoing webhook

*For any* `WebhookConfig` with a non-empty `events` list, every event type in that list must cause a webhook task to be enqueued when that event occurs, and event types not in the list must not cause a task to be enqueued.

**Validates: Requirement 4.4**

### Property 11: Primary identifier controls tool call arguments

*For any* `CRMConfig` with `primary_identifier` set to `email`, `user_id`, or `custom`, the identifier value substituted into tool URL templates and passed as the lookup key must match the field specified by `primary_identifier` from the available user context (widget payload or `extra_fields`).

**Validates: Requirement 5.1**

### Property 12: Widget extra_fields reach agent context

*For any* `extra_fields` dict passed via `JeevesWidget.identify()`, those key-value pairs must appear in the `/widget/chat` POST body and be present in the agent's system prompt context for that conversation turn.

**Validates: Requirement 5.2**

### Property 13: Write-back behavior matches configured type

*For any* `WriteBackConfig`, after `writeback_conversation` runs:
- When `type=hubspot_note`: a HubSpot note creation API call must be made with a non-empty LLM-generated summary.
- When `type=webhook`: an HTTP POST must be made to `webhook_url` with the summary in the payload.
- When `type=off`: no HubSpot note call and no webhook POST must occur.

**Validates: Requirements 6.1, 6.2, 6.4**

---

## Error Handling

### Connector errors

- All connector functions raise a typed `ConnectorError(provider, operation, status_code, message)` exception on failure.
- `routes_integrations.py` catches `ConnectorError` and returns HTTP 502 with a structured error body.
- `agent.py` catches connector errors during tool dispatch and returns a graceful message to the user rather than propagating the exception.
- Timeout (10 s) raises `httpx.TimeoutException`, which is caught and re-raised as `ConnectorError`.

### Credential decryption errors

- If `crypto.decrypt()` raises (corrupted ciphertext, wrong key), the connector raises `ConnectorError` with `operation="decrypt"`.
- This prevents the connector from making API calls with garbage credentials.

### Incoming webhook errors

- If the incoming webhook call fails (timeout, non-2xx, network error), the agent logs the error and continues with empty context — it does not block the conversation.
- Timeout for incoming webhook is 5 s (shorter than the 10 s connector timeout) to minimize user-visible latency.

### Outgoing webhook / write-back errors

- Celery tasks retry up to 3 times with exponential backoff (10 s, 30 s, 90 s).
- After 3 failures, the task is marked as failed and the error is logged to `AgentToolLog` with `tool_name="outgoing_webhook"` or `"writeback"`.
- Failures do not affect the conversation response already delivered to the user.

### Tool provisioning errors

- If `provision_tools` fails mid-way (e.g., duplicate name), it rolls back the transaction and raises, leaving no partial tool rows.
- The connect endpoint returns HTTP 500 with the error; the `NativeConnector` row is not persisted.

---

## Testing Strategy

### Dual testing approach

Both unit tests and property-based tests are required. Unit tests cover specific examples, integration points, and error conditions. Property tests verify universal correctness across randomized inputs.

### Property-based testing library

Use **Hypothesis** (Python) for all property tests. Minimum 100 iterations per property (`settings(max_examples=100)`).

Each property test must be tagged with a comment:
```python
# Feature: integrations-upgrade, Property N: <property_text>
```

### Unit tests (`api/tests/test_integrations_*.py`)

- `test_crypto.py`: encrypt/decrypt round-trip, ciphertext ≠ plaintext, wrong-key error.
- `test_shopify.py`: mock httpx responses, verify URL construction, idempotency header, timeout setting.
- `test_woocommerce.py`: mock httpx, verify Basic auth header, v3 URL path.
- `test_stripe.py`: mock Stripe SDK, verify idempotency_key passed to `modify`.
- `test_registry.py`: provision/deprovision for each provider, verify tool names and enabled state.
- `test_webhook.py`: HMAC signature computation, incoming context merge, outgoing task enqueue.
- `test_writeback.py`: HubSpot note creation, webhook POST, no-op when type=off.
- `test_identifier.py`: primary_identifier substitution for email/user_id/custom.

### Property tests (`api/tests/test_properties_integrations.py`)

Each correctness property from the design maps to exactly one `@given`-decorated test:

```python
# Feature: integrations-upgrade, Property 1: Credential encryption round-trip
@given(st.dictionaries(st.text(), st.text()))
@settings(max_examples=100)
def test_credential_encryption_round_trip(creds):
    plaintext = json.dumps(creds)
    ciphertext = crypto.encrypt(plaintext)
    assert crypto.decrypt(ciphertext) == plaintext
    assert ciphertext != plaintext

# Feature: integrations-upgrade, Property 3: Write operations carry idempotency keys
@given(st.text(min_size=1), st.text(min_size=1))
@settings(max_examples=100)
def test_idempotency_key_passed(order_id, idem_key):
    # mock httpx, call update_shipping_address, assert header present
    ...

# Feature: integrations-upgrade, Property 4: Tool auto-provisioning on connect
@given(st.sampled_from(["shopify", "woocommerce", "stripe"]))
@settings(max_examples=100)
def test_provision_creates_expected_tools(provider):
    # in-memory SQLite session, call provision_tools, assert tool names match spec
    ...

# ... one test per property
```

### Integration tests

- End-to-end test: connect Shopify (mocked), send a chat message asking about orders, verify the agent calls the `shopify_get_orders` tool and returns order data.
- End-to-end test: conversation ends, verify `writeback_conversation` task is enqueued with correct `session_id`.
