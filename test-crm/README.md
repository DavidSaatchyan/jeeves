# Test CRM

Standalone mock CRM system for testing Jeeves AI agent integrations.

## What is this

A fully functional CRM application with realistic customer data, orders, and activity logs. Designed to be used as the "external CRM" that Jeeves connects to — so you can test real integration scenarios without needing HubSpot, Salesforce, or any real CRM account.

## Run

```bash
# Install dependencies (same as Jeeves, plus fastapi + uvicorn)
pip install fastapi uvicorn sqlalchemy

# Start on port 8001
uvicorn test_crm_app:app --host 0.0.0.0 --port 8001 --reload

# Open admin UI
open http://localhost:8001
```

## Data

**15 realistic customers** seeded automatically on first run:
- Different plans (starter, business, enterprise)
- Different statuses (active, trial, churned, suspended)
- Different industries (SaaS, Retail, Healthcare, Finance, etc.)
- Realistic MRR, lifetime value, order counts
- Notes and tags for each customer

**Orders** linked to customers with statuses (pending, processing, shipped, delivered, cancelled)

**Activity logs** (7 days of daily login data) for proactive engine testing:
- Normal customers: steady activity
- At-risk customer (cust_jack_010): declining activity over 7 days → triggers proactive message
- Churned customer (cust_frank_006): zero recent activity
- Trial customer (cust_carol_003): high engagement

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/customers` | List all customers (filter by `?status=active&plan=business`) |
| GET | `/customers/{user_id}` | Get customer by ID or external_id |
| POST | `/customers` | Create new customer |
| PATCH | `/customers/{user_id}/plan` | Update plan (write test) |
| PATCH | `/customers/{user_id}/status` | Update status (write test) |
| DELETE | `/customers/{user_id}` | Delete customer |
| GET | `/customers/{user_id}/orders` | Get customer orders |
| GET | `/orders/{order_id}` | Get order by ID or number |
| PATCH | `/orders/{order_id}/status` | Update order status |
| POST | `/orders` | Create order |
| GET | `/activity/{user_id}` | Activity series for proactive engine |
| GET | `/health` | Health check |

## Use with Jeeves

In Jeeves admin panel → Integrations → CRM → Custom REST API:

**Read URL:**
```
http://localhost:8001/customers/{user_id}
```

**Write URL:**
```
http://localhost:8001/customers/{user_id}/plan
```

**Fields for Jeeves:**
- `plan` — subscription plan (starter/business/enterprise)
- `status` — customer status (active/trial/churned)
- `mrr` — monthly recurring revenue
- `orders_count` — number of orders
- `name` — customer name
- `email` — customer email
- `company` — company name

**Proactive Engine Metric URL:**
```
http://localhost:8001/activity/{id}
```

Response format: `{"data":{"series":[8,6,5,3,2,1,0]}}` — last value = today

## Test scenarios

1. **Read customer data**: Ask Jeeves "What's my plan?" → it calls CRM and answers
2. **Update plan**: Ask Jeeves "Change my plan to enterprise" → agent calls PATCH endpoint
3. **Check orders**: Ask Jeeves "What orders do I have?" → agent calls /customers/{id}/orders
4. **Proactive trigger**: At-risk customer (cust_jack_010) has declining activity → Jeeves sends proactive message

## Reset data

Delete `test_crm.db` and restart — seed data will be recreated.
