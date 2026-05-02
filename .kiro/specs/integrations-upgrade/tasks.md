# Implementation Plan: Integrations Upgrade

## Overview

Expand Jeeves from a single REST+HubSpot model into a multi-connector platform: Shopify, WooCommerce, Stripe, configurable webhooks, customer identifier control, and conversation write-back. All implemented in Python with FastAPI + SQLAlchemy + Celery.

## Tasks

- [x] 1. Database migrations and model extensions
  - Add `native_connectors`, `webhook_configs`, `writeback_configs` tables to `api/app/models.py`
  - Add `primary_identifier` column to `crm_config` table
  - Add `session_id` (UUID, indexed) and `extra_fields` (JSONB) columns to `chat_logs` table
  - Write Alembic migration script (or raw SQL in `scripts/`) for all schema changes
  - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1_

- [x] 2. Implement `api/app/crypto.py`
  - [x] 2.1 Implement `encrypt(plaintext: str) -> str` and `decrypt(ciphertext: str) -> str` using `cryptography.fernet`
    - Load Fernet key from `settings.fernet_key` (env var `FERNET_KEY`)
    - Raise `ConnectorError(operation="decrypt")` on decryption failure
    - _Requirements: 1.1, 3.2, 7.1_
  - [ ]* 2.2 Write property test for credential encryption round-trip
    - **Property 1: Credential encryption round-trip**
    - **Validates: Requirements 1.1, 3.2, 7.1**
    - File: `api/tests/test_properties_integrations.py`
    - `@given(st.dictionaries(st.text(), st.text()))`, `@settings(max_examples=100)`

- [x] 3. Implement connector modules
  - [x] 3.1 Implement `api/app/connectors/shopify.py`
    - `get_orders_by_email`, `get_order`, `update_shipping_address`, `cancel_order`
    - Use `httpx.AsyncClient(timeout=10.0)` against `https://{shop}/admin/api/2024-01/`
    - Pass idempotency key as `X-Shopify-Idempotency-Key` header on mutating calls
    - Catch `httpx.TimeoutException` → raise `ConnectorError`
    - _Requirements: 1.2, 1.3, 1.4, 1.5_
  - [ ]* 3.2 Write property test for Shopify idempotency key propagation
    - **Property 3: Write operations carry idempotency keys**
    - **Validates: Requirements 1.4, 1.5**
    - Mock httpx, assert header present in outgoing request
  - [ ]* 3.3 Write unit tests for Shopify connector (`api/tests/test_shopify.py`)
    - Mock httpx responses, verify URL construction, timeout setting, error handling
    - _Requirements: 1.2, 1.3, 1.4, 1.5_
  - [x] 3.4 Implement `api/app/connectors/woocommerce.py`
    - `get_orders_by_email`, `get_order`, `update_order_status`, `get_customer`
    - WooCommerce REST API v3 with HTTP Basic auth (`consumer_key:consumer_secret`)
    - _Requirements: 2.1, 2.2_
  - [ ]* 3.5 Write property test for WooCommerce v3 URL and Basic auth
    - **Property 6: WooCommerce connector uses v3 REST with Basic auth**
    - **Validates: Requirements 2.1**
    - Assert URL contains `/wp-json/wc/v3/` and `Authorization` header is valid Basic auth
  - [ ]* 3.6 Write property test for order lookup email isolation
    - **Property 2: Connector order lookup by email**
    - **Validates: Requirements 1.3, 2.2**
    - `@given(st.emails(), st.emails())` — assert no cross-customer data leakage
  - [ ]* 3.7 Write unit tests for WooCommerce connector (`api/tests/test_woocommerce.py`)
    - Mock httpx, verify Basic auth header, v3 URL path, error handling
    - _Requirements: 2.1, 2.2_
  - [x] 3.8 Implement `api/app/connectors/stripe_connector.py`
    - `get_subscription`, `get_next_invoice`, `cancel_at_period_end`
    - Use `stripe` Python SDK; set `stripe.api_key` per-call from decrypted credentials
    - Pass `idempotency_key` to `stripe.Subscription.modify`
    - _Requirements: 3.1, 3.2_
  - [ ]* 3.9 Write property test for Stripe idempotency key
    - **Property 3: Write operations carry idempotency keys (Stripe)**
    - **Validates: Requirements 3.1**
    - Mock Stripe SDK, assert `idempotency_key` passed to `modify`
  - [ ]* 3.10 Write unit tests for Stripe connector (`api/tests/test_stripe.py`)
    - Mock Stripe SDK, verify idempotency_key, error handling
    - _Requirements: 3.1, 3.2_

- [x] 4. Implement `api/app/connectors/registry.py`
  - [x] 4.1 Define `TOOL_SPECS` dict with canonical AgentTool specs for `shopify`, `woocommerce`, `stripe`
    - _Requirements: 1.6, 1.7_
  - [x] 4.2 Implement `provision_tools(db, tenant_id, provider)` — creates AgentTool rows, rolls back on failure
    - All created tools must be enabled
    - _Requirements: 1.6_
  - [x] 4.3 Implement `deprovision_tools(db, tenant_id, provider)` — deletes all AgentTool rows for provider
    - _Requirements: 1.7_
  - [x]* 4.4 Write property test for tool auto-provisioning
    - **Property 4: Tool auto-provisioning on connect**
    - **Validates: Requirement 1.6**
    - `@given(st.sampled_from(["shopify", "woocommerce", "stripe"]))`, in-memory SQLite session
  - [x]* 4.5 Write property test for tool deprovisioning round-trip
    - **Property 5: Tool deprovisioning round-trip**
    - **Validates: Requirement 1.7**
    - Provision then deprovision, assert zero AgentTool rows remain
  - [x]* 4.6 Write unit tests for registry (`api/tests/test_registry.py`)
    - Provision/deprovision for each provider, verify tool names and enabled state
    - _Requirements: 1.6, 1.7_

- [x] 5. Checkpoint — Ensure all connector and registry tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement `api/app/routes_integrations.py`
  - [x] 6.1 Create FastAPI router with all 8 endpoints (GET/POST/DELETE for native connectors, webhook config, writeback config)
    - Encrypt credentials via `crypto.encrypt` before DB write; never return raw credentials
    - Call `registry.provision_tools` on connect, `registry.deprovision_tools` on disconnect
    - Catch `ConnectorError` → return HTTP 502
    - _Requirements: 1.1, 1.6, 1.7, 4.1, 6.1_
  - [x] 6.2 Implement `POST /integrations/native/{provider}/test` — test connector connectivity
    - _Requirements: 1.2, 2.1, 3.1_
  - [x] 6.3 Register router in `api/app/main.py`
    - _Requirements: 1.1_
  - [ ]* 6.4 Write unit tests for integration routes (`api/tests/test_integrations_routes.py`)

- [x] 7. Extend `api/app/crm.py` to delegate to native connectors
  - [x] 7.1 Modify `crm.py` to check for `NativeConnector` rows and delegate to `connectors/shopify.py`, `connectors/woocommerce.py`, `connectors/stripe_connector.py` when present
    - Decrypt credentials inside connector modules only
    - _Requirements: 1.2, 2.2, 3.1_
  - [x] 7.2 Implement primary identifier substitution: read `CRMConfig.primary_identifier` and use the correct field (`email`, `user_id`, or custom field from `extra_fields`) as the lookup key
    - _Requirements: 5.1_
  - [x]* 7.3 Write property test for primary identifier control
    - **Property 11: Primary identifier controls tool call arguments**
    - **Validates: Requirement 5.1**
    - `@given(st.sampled_from(["email", "user_id", "custom"]))` — assert correct field used
  - [x]* 7.4 Write unit tests for identifier substitution (`api/tests/test_identifier.py`)
    - Test email/user_id/custom modes
    - _Requirements: 5.1_

- [x] 8. Extend `frontend/widget.js` and chat route for `extra_fields`
  - [x] 8.1 Extend `JeevesWidget.identify()` to accept arbitrary extra fields and merge them into the `/widget/chat` POST body as `extra_fields: {...}`
    - _Requirements: 5.2_
  - [x] 8.2 Extend `/widget/chat` handler in `api/app/channels/widget.py` to read `extra_fields` from request body, store in `ChatLog.extra_fields`, and pass to agent context
    - _Requirements: 5.2_
  - [x]* 8.3 Write property test for widget extra_fields propagation
    - **Property 12: Widget extra_fields reach agent context**
    - **Validates: Requirement 5.2**
    - `@given(st.dictionaries(st.text(min_size=1), st.text()))` — assert fields appear in system prompt context

- [x] 9. Implement webhook support in `api/app/routes_chat.py` and `worker/tasks.py`
  - [x] 9.1 Implement `fetch_incoming_webhook_context(db, tenant_id, user_id, extra_fields)` in a new `api/app/webhooks.py` module
    - POST to `incoming_url` with HMAC-SHA256 signed payload, timeout 5 s
    - Merge response fields via `field_mapping` into agent context
    - On failure (timeout, non-2xx): log and return empty dict — do not block conversation
    - _Requirements: 4.1_
  - [x] 9.2 Call `fetch_incoming_webhook_context` at conversation start in `agent.py` before first LLM call
    - _Requirements: 4.1_
  - [x] 9.3 Implement `send_outgoing_webhook` Celery task in `worker/tasks.py`
    - Sign payload with HMAC-SHA256 → `X-Jeeves-Signature: sha256=<hex>` header
    - Retry 3× with exponential backoff (10 s, 30 s, 90 s)
    - Log failure to `AgentToolLog` after 3 retries
    - _Requirements: 4.2, 4.3, 4.4_
  - [x] 9.4 Enqueue `send_outgoing_webhook.delay(...)` in `routes_chat.py` after agent.run() for `conversation.started`, `conversation.ended`, `action.called` events — only when event is in `WebhookConfig.events`
    - _Requirements: 4.2, 4.4_
  - [x]* 9.5 Write property test for outgoing webhook HMAC signature
    - **Property 9: Outgoing webhook payload is HMAC-SHA256 signed**
    - **Validates: Requirement 4.3**
    - `@given(st.binary())` — assert `X-Jeeves-Signature` header matches computed HMAC
  - [x]* 9.6 Write property test for async webhook enqueue
    - **Property 8: Outgoing webhook and write-back are enqueued asynchronously**
    - **Validates: Requirements 4.2, 6.3**
    - Mock `.delay()`, assert called (not inline execution)
  - [x]* 9.7 Write property test for event filtering
    - **Property 10: All configured events trigger outgoing webhook**
    - **Validates: Requirement 4.4**
    - `@given(st.lists(st.sampled_from([...events...])))` — assert enqueue iff event in config
  - [x]* 9.8 Write property test for incoming webhook context injection
    - **Property 7: Incoming webhook context injected at conversation start**
    - **Validates: Requirement 4.1**
    - Mock HTTP POST, assert called before LLM and fields appear in context
  - [x]* 9.9 Write unit tests for webhook module (`api/tests/test_webhooks.py`)
    - HMAC signature computation, incoming context merge, outgoing task enqueue
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 10. Implement write-back in `worker/tasks.py`
  - [x] 10.1 Implement `writeback_conversation` Celery task
    - Read `WriteBackConfig` for tenant; if `type=off`, return immediately
    - Generate LLM summary of conversation turns for the given `session_id`
    - `type=hubspot_note`: call HubSpot note creation API with summary
    - `type=webhook`: POST summary to `webhook_url`
    - Retry 3× with exponential backoff; log failure to `AgentToolLog`
    - _Requirements: 6.1, 6.2, 6.4_
  - [x] 10.2 Enqueue `writeback_conversation.delay(tenant_id, session_id)` in `routes_chat.py` on `conversation.ended`
    - _Requirements: 6.3_
  - [x]* 10.3 Write property test for write-back behavior by type
    - **Property 13: Write-back behavior matches configured type**
    - **Validates: Requirements 6.1, 6.2, 6.4**
    - `@given(st.sampled_from(["off", "hubspot_note", "webhook"]))` — assert correct side-effect per type
  - [x]* 10.4 Write unit tests for write-back (`api/tests/test_writeback.py`)
    - HubSpot note creation, webhook POST, no-op when type=off
    - _Requirements: 6.1, 6.2, 6.4_

- [x] 11. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Wire everything together and integration tests
  - [x] 12.1 Ensure `session_id` is generated at conversation start and propagated through `ChatLog`, agent context, and Celery task payloads
    - _Requirements: 4.2, 6.3_
  - [x] 12.2 Ensure `agent.py` catches `ConnectorError` during tool dispatch and returns a graceful user-facing message
    - _Requirements: 1.2, 2.2, 3.1_
  - [ ]* 12.3 Write end-to-end integration test: connect Shopify (mocked), send chat asking about orders, verify agent calls `shopify_get_orders` tool and returns order data
    - _Requirements: 1.2, 1.3, 1.6_
  - [ ]* 12.4 Write end-to-end integration test: conversation ends, verify `writeback_conversation` task enqueued with correct `session_id`
    - _Requirements: 6.3_

- [x] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis with `@settings(max_examples=100)` and must be tagged with `# Feature: integrations-upgrade, Property N: <text>`
- Credentials must never be decrypted outside connector modules
- All mutating connector calls must carry idempotency keys
- Integration route tests (`test_integrations_routes.py`) require Docker with PostgreSQL and are skipped in local runs
