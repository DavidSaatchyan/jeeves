"""Test CRM — standalone mock CRM system for testing Jeeves integrations.

Run: uvicorn test_crm_app:app --host 0.0.0.0 --port 8001 --reload
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = "sqlite:///./test_crm.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid.uuid4())
    external_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    company = Column(Text)
    plan = Column(String(32), default="starter")
    status = Column(String(32), default="active")
    mrr = Column(Float, default=0)
    lifetime_value = Column(Float, default=0)
    orders_count = Column(Integer, default=0)
    last_login = Column(DateTime)
    notes = Column(Text)
    tags = Column(Text, default="[]")  # JSON string
    custom_fields = Column(Text, default="{}")  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid.uuid4())
    customer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    order_number = Column(String(32), nullable=False)
    status = Column(String(32), default="pending")
    total = Column(Float, nullable=False)
    items = Column(Text, default="[]")  # JSON string
    shipping_address = Column(Text)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ActivityLog(Base):
    __tablename__ = "activity_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid.uuid4())
    customer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    date = Column(DateTime, nullable=False)
    logins = Column(Integer, default=0)
    page_views = Column(Integer, default=0)


Base.metadata.create_all(bind=engine)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Test CRM", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Pydantic schemas ──────────────────────────────────────────────────────────
class CustomerIn(BaseModel):
    external_id: str
    name: str
    email: str
    company: str | None = None
    plan: str = "starter"
    status: str = "active"
    mrr: float = 0
    lifetime_value: float = 0
    notes: str | None = None
    tags: list[str] = []
    custom_fields: dict = {}


class CustomerOut(CustomerIn):
    id: str
    orders_count: int
    last_login: str | None
    created_at: str
    updated_at: str
    class Config:
        from_attributes = True


class OrderIn(BaseModel):
    customer_id: str
    order_number: str
    status: str = "pending"
    total: float
    items: list[dict] = []
    shipping_address: dict | None = None


class OrderOut(OrderIn):
    id: str
    created_at: str
    class Config:
        from_attributes = True


class UpdatePlanIn(BaseModel):
    plan: str


class UpdateStatusIn(BaseModel):
    status: str


# ── Seed data ─────────────────────────────────────────────────────────────────
def seed_data():
    """Insert realistic test customers if table is empty."""
    db = SessionLocal()
    if db.query(Customer).first():
        db.close()
        return

    customers = [
        {
            "external_id": "cust_alice_001",
            "name": "Alice Johnson",
            "email": "alice@techcorp.com",
            "company": "TechCorp Inc.",
            "plan": "enterprise",
            "status": "active",
            "mrr": 499.0,
            "lifetime_value": 14970.0,
            "orders_count": 23,
            "last_login": datetime.utcnow() - timedelta(hours=2),
            "notes": "VIP customer. CTO at TechCorp. Very technical, asks about API limits.",
            "tags": ["vip", "enterprise", "tech"],
            "custom_fields": {"industry": "SaaS", "team_size": 150, "onboarding_date": "2023-06-15"},
        },
        {
            "external_id": "cust_bob_002",
            "name": "Bob Martinez",
            "email": "bob@retailplus.com",
            "company": "RetailPlus",
            "plan": "business",
            "status": "active",
            "mrr": 199.0,
            "lifetime_value": 4776.0,
            "orders_count": 12,
            "last_login": datetime.utcnow() - timedelta(hours=6),
            "notes": "Growing business. Interested in analytics features.",
            "tags": ["business", "growth"],
            "custom_fields": {"industry": "Retail", "team_size": 45, "onboarding_date": "2024-01-10"},
        },
        {
            "external_id": "cust_carol_003",
            "name": "Carol Chen",
            "email": "carol@designstudio.io",
            "company": "Design Studio",
            "plan": "starter",
            "status": "trial",
            "mrr": 0,
            "lifetime_value": 0,
            "orders_count": 0,
            "last_login": datetime.utcnow() - timedelta(hours=1),
            "notes": "Trial user. Very engaged in first week. May convert.",
            "tags": ["trial", "design", "hot-lead"],
            "custom_fields": {"industry": "Design", "team_size": 5, "onboarding_date": "2024-12-01"},
        },
        {
            "external_id": "cust_dave_004",
            "name": "Dave Thompson",
            "email": "dave@logistics-hub.com",
            "company": "Logistics Hub",
            "plan": "business",
            "status": "active",
            "mrr": 199.0,
            "lifetime_value": 2388.0,
            "orders_count": 8,
            "last_login": datetime.utcnow() - timedelta(days=1),
            "notes": "Uses shipping integration heavily. Had 1 support ticket last month.",
            "tags": ["business", "logistics"],
            "custom_fields": {"industry": "Logistics", "team_size": 30, "onboarding_date": "2024-08-20"},
        },
        {
            "external_id": "cust_eva_005",
            "name": "Eva Kowalski",
            "email": "eva@healthfirst.org",
            "company": "HealthFirst",
            "plan": "enterprise",
            "status": "active",
            "mrr": 499.0,
            "lifetime_value": 9980.0,
            "orders_count": 15,
            "last_login": datetime.utcnow() - timedelta(hours=4),
            "notes": "Healthcare compliance requirements. Needs SOC2 certification.",
            "tags": ["enterprise", "healthcare", "compliance"],
            "custom_fields": {"industry": "Healthcare", "team_size": 200, "onboarding_date": "2024-03-05"},
        },
        {
            "external_id": "cust_frank_006",
            "name": "Frank Williams",
            "email": "frank@startup.co",
            "company": "Startup Co",
            "plan": "starter",
            "status": "churned",
            "mrr": 0,
            "lifetime_value": 297.0,
            "orders_count": 2,
            "last_login": datetime.utcnow() - timedelta(days=45),
            "notes": "Churned after 3 months. Reason: moved to competitor. May win back.",
            "tags": ["churned", "startup"],
            "custom_fields": {"industry": "Tech", "team_size": 3, "onboarding_date": "2024-06-01", "churn_date": "2024-09-01", "churn_reason": "competitor"},
        },
        {
            "external_id": "cust_grace_007",
            "name": "Grace Lee",
            "email": "grace@eduplatform.com",
            "company": "EduPlatform",
            "plan": "business",
            "status": "active",
            "mrr": 199.0,
            "lifetime_value": 3582.0,
            "orders_count": 9,
            "last_login": datetime.utcnow() - timedelta(hours=3),
            "notes": "Education platform. Seasonal traffic spikes during semester.",
            "tags": ["business", "education"],
            "custom_fields": {"industry": "Education", "team_size": 60, "onboarding_date": "2024-05-15"},
        },
        {
            "external_id": "cust_henry_008",
            "name": "Henry Patel",
            "email": "henry@fintech.io",
            "company": "FinTech Solutions",
            "plan": "enterprise",
            "status": "active",
            "mrr": 499.0,
            "lifetime_value": 19960.0,
            "orders_count": 31,
            "last_login": datetime.utcnow() - timedelta(hours=0.5),
            "notes": "Power user. Uses API extensively. Has asked about rate limit increases.",
            "tags": ["enterprise", "fintech", "power-user", "api-heavy"],
            "custom_fields": {"industry": "Finance", "team_size": 80, "onboarding_date": "2023-11-01"},
        },
        {
            "external_id": "cust_iris_009",
            "name": "Iris Nakamura",
            "email": "iris@foodchain.com",
            "company": "Global Food Chain",
            "plan": "business",
            "status": "active",
            "mrr": 199.0,
            "lifetime_value": 1194.0,
            "orders_count": 4,
            "last_login": datetime.utcnow() - timedelta(days=2),
            "notes": "Restaurant chain. Interested in multi-location support.",
            "tags": ["business", "food", "multi-location"],
            "custom_fields": {"industry": "Food & Beverage", "team_size": 500, "onboarding_date": "2024-09-10"},
        },
        {
            "external_id": "cust_jack_010",
            "name": "Jack Robinson",
            "email": "jack@autoparts.com",
            "company": "AutoParts Direct",
            "plan": "starter",
            "status": "active",
            "mrr": 29.0,
            "lifetime_value": 348.0,
            "orders_count": 3,
            "last_login": datetime.utcnow() - timedelta(days=5),
            "notes": "Small business owner. Low engagement lately. At risk of churn.",
            "tags": ["starter", "at-risk", "low-engagement"],
            "custom_fields": {"industry": "Automotive", "team_size": 2, "onboarding_date": "2024-10-01"},
        },
        {
            "external_id": "cust_kate_011",
            "name": "Kate Sullivan",
            "email": "kate@fashionhouse.com",
            "company": "Fashion House",
            "plan": "business",
            "status": "active",
            "mrr": 199.0,
            "lifetime_value": 5970.0,
            "orders_count": 18,
            "last_login": datetime.utcnow() - timedelta(hours=8),
            "notes": "E-commerce fashion brand. High order volume during sales events.",
            "tags": ["business", "fashion", "high-volume"],
            "custom_fields": {"industry": "Fashion", "team_size": 25, "onboarding_date": "2024-02-14"},
        },
        {
            "external_id": "cust_leo_012",
            "name": "Leo Zhang",
            "email": "leo@gamedev.studio",
            "company": "GameDev Studio",
            "plan": "starter",
            "status": "trial",
            "mrr": 0,
            "lifetime_value": 0,
            "orders_count": 0,
            "last_login": datetime.utcnow() - timedelta(hours=12),
            "notes": "Gaming startup. Evaluating for community support. Good upsell potential.",
            "tags": ["trial", "gaming", "upsell-potential"],
            "custom_fields": {"industry": "Gaming", "team_size": 12, "onboarding_date": "2024-11-20"},
        },
        {
            "external_id": "cust_mia_013",
            "name": "Mia Anderson",
            "email": "mia@realestate.pro",
            "company": "Real Estate Pro",
            "plan": "business",
            "status": "active",
            "mrr": 199.0,
            "lifetime_value": 2985.0,
            "orders_count": 7,
            "last_login": datetime.utcnow() - timedelta(days=3),
            "notes": "Real estate agency. Uses CRM integration. Happy customer.",
            "tags": ["business", "real-estate", "happy"],
            "custom_fields": {"industry": "Real Estate", "team_size": 15, "onboarding_date": "2024-07-01"},
        },
        {
            "external_id": "cust_noah_014",
            "name": "Noah Kim",
            "email": "noah@travelco.com",
            "company": "Travel Co",
            "plan": "starter",
            "status": "suspended",
            "mrr": 0,
            "lifetime_value": 174.0,
            "orders_count": 1,
            "last_login": datetime.utcnow() - timedelta(days=60),
            "notes": "Suspended for billing issues. Contacted but no response.",
            "tags": ["suspended", "travel", "billing-issue"],
            "custom_fields": {"industry": "Travel", "team_size": 8, "onboarding_date": "2024-04-01", "suspend_date": "2024-10-01"},
        },
        {
            "external_id": "cust_olivia_015",
            "name": "Olivia Brown",
            "email": "olivia@nonprofit.org",
            "company": "Community Nonprofit",
            "plan": "starter",
            "status": "active",
            "mrr": 29.0,
            "lifetime_value": 522.0,
            "orders_count": 5,
            "last_login": datetime.utcnow() - timedelta(days=1),
            "notes": "Nonprofit org. On discount plan. Very active in community forum.",
            "tags": ["starter", "nonprofit", "discount", "community"],
            "custom_fields": {"industry": "Nonprofit", "team_size": 10, "onboarding_date": "2024-03-20"},
        },
    ]

    for c in customers:
        tags = json.dumps(c.pop("tags"))
        custom = json.dumps(c.pop("custom_fields"))
        customer = Customer(**c, tags=tags, custom_fields=custom)
        db.add(customer)

    db.commit()

    # Create orders for active customers with orders_count > 0
    customers_list = db.query(Customer).all()
    order_counter = 1
    for c in customers_list:
        if c.orders_count > 0:
            num_orders = min(c.orders_count, 5)  # Cap at 5 actual order records
            for i in range(num_orders):
                statuses = ["delivered", "delivered", "delivered", "shipped", "processing"]
                status = statuses[i % len(statuses)]
                total = round(29.0 + hash(f"{c.external_id}-{i}") % 500, 2)
                order = Order(
                    customer_id=c.id,
                    order_number=f"ORD-2024-{order_counter:04d}",
                    status=status,
                    total=total,
                    items=json.dumps([
                        {"name": f"Product {chr(65 + (i % 26))}", "qty": 1 + (i % 3), "price": round(total / (1 + (i % 3)), 2)}
                    ]),
                    shipping_address=json.dumps({
                        "street": f"{100 + order_counter} Main St",
                        "city": ["New York", "London", "Tokyo", "Berlin", "Sydney"][order_counter % 5],
                        "country": ["US", "UK", "JP", "DE", "AU"][order_counter % 5],
                        "zip": f"{10000 + order_counter}",
                    }) if status != "cancelled" else None,
                    created_at=datetime.utcnow() - timedelta(days=order_counter * 7),
                )
                db.add(order)
                order_counter += 1

    # Create activity logs for proactive testing
    # Most customers: normal activity
    # cust_jack_010 (at-risk): declining activity over last 7 days
    # cust_frank_006 (churned): no recent activity
    now = datetime.utcnow()
    for c in customers_list:
        if c.status == "churned":
            # No recent activity for churned
            for d in range(7):
                activity = ActivityLog(
                    customer_id=c.id,
                    date=now - timedelta(days=d),
                    logins=0,
                    page_views=0,
                )
                db.add(activity)
        elif c.external_id == "cust_jack_010":
            # Declining: 8, 6, 5, 3, 2, 1, 0 (trigger proactive at 30% threshold)
            declines = [8, 6, 5, 3, 2, 1, 0]
            for d in range(7):
                activity = ActivityLog(
                    customer_id=c.id,
                    date=now - timedelta(days=6 - d),
                    logins=declines[d],
                    page_views=declines[d] * 3,
                )
                db.add(activity)
        elif c.external_id == "cust_carol_003":
            # Trial user, high activity
            for d in range(7):
                activity = ActivityLog(
                    customer_id=c.id,
                    date=now - timedelta(days=d),
                    logins=5 + d,
                    page_views=20 + d * 5,
                )
                db.add(activity)
        else:
            # Normal steady activity
            base = 3 + (hash(c.external_id) % 5)
            for d in range(7):
                activity = ActivityLog(
                    customer_id=c.id,
                    date=now - timedelta(days=d),
                    logins=max(1, base + (hash(f"{c.id}-{d}") % 3) - 1),
                    page_views=max(2, base * 3 + (hash(f"{c.id}-{d}") % 5)),
                )
                db.add(activity)

    db.commit()
    db.close()
    print("[test-crm] Seed data loaded.", flush=True)


seed_data()


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "test-crm"}


# ── Customers ─────────────────────────────────────────────────────────────────

@app.get("/customers")
def list_customers(status: str | None = None, plan: str | None = None):
    """List all customers. Filter by status or plan."""
    db = SessionLocal()
    q = db.query(Customer)
    if status:
        q = q.filter(Customer.status == status)
    if plan:
        q = q.filter(Customer.plan == plan)
    customers = q.all()
    result = []
    for c in customers:
        result.append({
            "id": str(c.id),
            "external_id": c.external_id,
            "name": c.name,
            "email": c.email,
            "company": c.company,
            "plan": c.plan,
            "status": c.status,
            "mrr": c.mrr,
            "lifetime_value": c.lifetime_value,
            "orders_count": c.orders_count,
            "last_login": c.last_login.isoformat() if c.last_login else None,
            "notes": c.notes,
            "tags": json.loads(c.tags) if c.tags else [],
            "custom_fields": json.loads(c.custom_fields) if c.custom_fields else {},
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        })
    db.close()
    return result


@app.get("/customers/{customer_id}")
def get_customer(customer_id: str):
    """Get customer by ID. Supports lookup by external_id (user_id)."""
    db = SessionLocal()
    c = db.query(Customer).filter(
        (Customer.id == customer_id) | (Customer.external_id == customer_id)
    ).first()
    if not c:
        db.close()
        raise HTTPException(404, f"Customer not found: {customer_id}")
    result = {
        "id": str(c.id),
        "external_id": c.external_id,
        "name": c.name,
        "email": c.email,
        "company": c.company,
        "plan": c.plan,
        "status": c.status,
        "mrr": c.mrr,
        "lifetime_value": c.lifetime_value,
        "orders_count": c.orders_count,
        "last_login": c.last_login.isoformat() if c.last_login else None,
        "notes": c.notes,
        "tags": json.loads(c.tags) if c.tags else [],
        "custom_fields": json.loads(c.custom_fields) if c.custom_fields else {},
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }
    db.close()
    return result


@app.patch("/customers/{customer_id}/plan")
def update_plan(customer_id: str, body: UpdatePlanIn):
    """Update customer plan (tests write capability)."""
    db = SessionLocal()
    c = db.query(Customer).filter(
        (Customer.id == customer_id) | (Customer.external_id == customer_id)
    ).first()
    if not c:
        db.close()
        raise HTTPException(404, f"Customer not found: {customer_id}")
    old_plan = c.plan
    c.plan = body.plan
    db.commit()
    db.close()
    return {"ok": True, "external_id": c.external_id, "old_plan": old_plan, "new_plan": body.plan}


@app.patch("/customers/{customer_id}/status")
def update_status(customer_id: str, body: UpdateStatusIn):
    """Update customer status."""
    db = SessionLocal()
    c = db.query(Customer).filter(
        (Customer.id == customer_id) | (Customer.external_id == customer_id)
    ).first()
    if not c:
        db.close()
        raise HTTPException(404, f"Customer not found: {customer_id}")
    old_status = c.status
    c.status = body.status
    db.commit()
    db.close()
    return {"ok": True, "external_id": c.external_id, "old_status": old_status, "new_status": body.status}


@app.post("/customers", status_code=201)
def create_customer(body: CustomerIn):
    """Create a new customer."""
    db = SessionLocal()
    existing = db.query(Customer).filter(Customer.external_id == body.external_id).first()
    if existing:
        db.close()
        raise HTTPException(409, f"Customer with external_id {body.external_id} already exists")
    c = Customer(
        **body.model_dump(exclude={"tags", "custom_fields"}),
        tags=json.dumps(body.tags),
        custom_fields=json.dumps(body.custom_fields),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    result = {
        "id": str(c.id),
        "external_id": c.external_id,
        "name": c.name,
        "email": c.email,
        "company": c.company,
        "plan": c.plan,
        "status": c.status,
        "mrr": c.mrr,
        "lifetime_value": c.lifetime_value,
        "orders_count": c.orders_count,
        "last_login": c.last_login.isoformat() if c.last_login else None,
        "notes": c.notes,
        "tags": body.tags,
        "custom_fields": body.custom_fields,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }
    db.close()
    return result


@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: str):
    """Delete a customer."""
    db = SessionLocal()
    c = db.query(Customer).filter(
        (Customer.id == customer_id) | (Customer.external_id == customer_id)
    ).first()
    if not c:
        db.close()
        raise HTTPException(404, f"Customer not found: {customer_id}")
    db.delete(c)
    db.commit()
    db.close()
    return {"ok": True, "deleted": customer_id}


# ── Orders ────────────────────────────────────────────────────────────────────

@app.get("/customers/{customer_id}/orders")
def get_orders(customer_id: str):
    """Get all orders for a customer."""
    db = SessionLocal()
    c = db.query(Customer).filter(
        (Customer.id == customer_id) | (Customer.external_id == customer_id)
    ).first()
    if not c:
        db.close()
        raise HTTPException(404, f"Customer not found: {customer_id}")
    orders = db.query(Order).filter(Order.customer_id == c.id).order_by(Order.created_at.desc()).all()
    result = []
    for o in orders:
        result.append({
            "id": str(o.id),
            "order_number": o.order_number,
            "status": o.status,
            "total": o.total,
            "items": json.loads(o.items) if o.items else [],
            "shipping_address": json.loads(o.shipping_address) if o.shipping_address else None,
            "created_at": o.created_at.isoformat(),
        })
    db.close()
    return result


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    """Get order by ID or order_number."""
    db = SessionLocal()
    o = db.query(Order).filter(
        (Order.id == order_id) | (Order.order_number == order_id)
    ).first()
    if not o:
        db.close()
        raise HTTPException(404, f"Order not found: {order_id}")
    result = {
        "id": str(o.id),
        "order_number": o.order_number,
        "customer_id": str(o.customer_id),
        "status": o.status,
        "total": o.total,
        "items": json.loads(o.items) if o.items else [],
        "shipping_address": json.loads(o.shipping_address) if o.shipping_address else None,
        "created_at": o.created_at.isoformat(),
    }
    db.close()
    return result


@app.patch("/orders/{order_id}/status")
def update_order_status(order_id: str, body: UpdateStatusIn):
    """Update order status (tests write capability)."""
    db = SessionLocal()
    o = db.query(Order).filter(
        (Order.id == order_id) | (Order.order_number == order_id)
    ).first()
    if not o:
        db.close()
        raise HTTPException(404, f"Order not found: {order_id}")
    old_status = o.status
    o.status = body.status
    db.commit()
    db.close()
    return {"ok": True, "order_number": o.order_number, "old_status": old_status, "new_status": body.status}


@app.post("/orders", status_code=201)
def create_order(body: OrderIn):
    """Create a new order."""
    db = SessionLocal()
    c = db.query(Customer).filter(
        (Customer.id == body.customer_id) | (Customer.external_id == body.customer_id)
    ).first()
    if not c:
        db.close()
        raise HTTPException(404, f"Customer not found: {body.customer_id}")
    order = Order(
        customer_id=c.id,
        order_number=body.order_number,
        status=body.status,
        total=body.total,
        items=json.dumps(body.items),
        shipping_address=json.dumps(body.shipping_address) if body.shipping_address else None,
    )
    db.add(order)
    c.orders_count += 1
    db.commit()
    db.refresh(order)
    result = {
        "id": str(order.id),
        "order_number": order.order_number,
        "customer_id": body.customer_id,
        "status": order.status,
        "total": order.total,
        "items": body.items,
        "shipping_address": body.shipping_address,
        "created_at": order.created_at.isoformat(),
    }
    db.close()
    return result


# ── Activity (for proactive engine testing) ───────────────────────────────────

@app.get("/activity/{external_id}")
def get_activity(external_id: str):
    """Get daily activity series for a customer. Used by Jeeves proactive engine.

    Returns format compatible with Jeeves expectations:
    {"data": {"series": [logins, ...]}} where last value = today
    """
    db = SessionLocal()
    c = db.query(Customer).filter(Customer.external_id == external_id).first()
    if not c:
        db.close()
        raise HTTPException(404, f"Customer not found: {external_id}")

    # Get last 7 days of activity, ordered by date ascending
    activities = (
        db.query(ActivityLog)
        .filter(ActivityLog.customer_id == c.id)
        .order_by(ActivityLog.date.asc())
        .all()
    )

    series = [a.logins for a in activities]
    page_views = [a.page_views for a in activities]

    db.close()
    return {
        "data": {
            "series": series,
            "page_views": page_views,
            "dates": [a.date.isoformat() for a in activities],
        }
    }


# ── Admin UI ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def admin_ui():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test CRM Admin</title>
<style>
:root{--bg:#0f1117;--surface:#1a1d27;--border:#2a2d3a;--accent:#6366f1;--text:#e2e8f0;--muted:#94a3b8;--green:#10b981;--red:#f87171;--amber:#f59e0b}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);padding:24px;font-size:14px}
h1{font-size:22px;font-weight:700;margin-bottom:4px}
.subtitle{color:var(--muted);margin-bottom:24px}
.tabs{display:flex;gap:8px;margin-bottom:20px}
.tab{padding:8px 16px;border-radius:8px;cursor:pointer;background:var(--surface);border:1px solid var(--border);color:var(--muted);font-size:13px;font-weight:500}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
table{width:100%;border-collapse:collapse;background:var(--surface);border-radius:12px;overflow:hidden;border:1px solid var(--border)}
th{padding:12px 16px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);border-bottom:1px solid var(--border)}
td{padding:10px 16px;border-bottom:1px solid var(--border);font-size:13px}
tr:hover td{background:rgba(99,102,241,0.04)}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}
.pill-active{color:var(--green);background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.2)}
.pill-churned{color:var(--red);background:rgba(248,113,113,0.1);border:1px solid rgba(248,113,113,0.2)}
.pill-trial{color:var(--amber);background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2)}
.pill-default{color:var(--muted);background:rgba(255,255,255,0.04);border:1px solid var(--border)}
.section{display:none}
.section.active{display:block}
code{background:var(--bg);padding:2px 6px;border-radius:4px;font-size:12px}
.help{background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.15);border-radius:12px;padding:16px;margin-bottom:20px;line-height:1.6}
.help h3{font-size:14px;margin-bottom:8px}
.help p{color:var(--muted);font-size:13px}
.endpoint{font-family:'SF Mono',monospace;font-size:12px;color:var(--accent)}
</style>
</head>
<body>
<h1>Test CRM</h1>
<div class="subtitle">Standalone CRM system for testing Jeeves integrations — port 8001</div>

<div class="help">
<h3>How Jeeves uses this CRM</h3>
<p><span class="endpoint">GET /customers/{user_id}</span> — Read customer profile (plan, status, MRR, etc.)</p>
<p><span class="endpoint">PATCH /customers/{user_id}/plan</span> — Update customer plan (write test)</p>
<p><span class="endpoint">GET /customers/{user_id}/orders</span> — Get customer orders</p>
<p><span class="endpoint">GET /orders/{order_id}</span> — Get order by ID</p>
<p><span class="endpoint">PATCH /orders/{order_id}/status</span> — Update order status (write test)</p>
<p><span class="endpoint">GET /activity/{user_id}</span> — Activity series for proactive engine</p>
</div>

<div class="tabs">
<div class="tab active" onclick="show('customers')">Customers (15)</div>
<div class="tab" onclick="show('orders')">Orders</div>
</div>

<div id="customers" class="section active">
<table>
<thead><tr><th>Name</th><th>Email</th><th>Company</th><th>Plan</th><th>Status</th><th>MRR</th><th>Orders</th><th>Last Login</th></tr></thead>
<tbody id="custBody"></tbody>
</table>
</div>

<div id="orders" class="section">
<table>
<thead><tr><th>Order #</th><th>Customer</th><th>Status</th><th>Total</th><th>Items</th><th>Date</th></tr></thead>
<tbody id="ordBody"></tbody>
</table>
</div>

<script>
function pillClass(s){return s==='active'?'pill-active':s==='churned'?'pill-churned':s==='trial'||s==='suspended'?'pill-trial':'pill-default'}
function show(id){document.querySelectorAll('.section').forEach(function(e){e.classList.remove('active')});document.querySelectorAll('.tab').forEach(function(e){e.classList.remove('active')});document.getElementById(id).classList.add('active');event.target.classList.add('active');if(id==='orders')loadOrders()}
async function load(){
const cs=await fetch('/customers').then(function(r){return r.json()});
document.getElementById('custBody').innerHTML=cs.map(function(c){
return '<tr><td><strong>'+c.name+'</strong><br><span style="color:var(--muted);font-size:11px">'+c.external_id+'</span></td><td>'+c.email+'</td><td>'+c.company+'</td><td>'+c.plan+'</td><td><span class="pill '+pillClass(c.status)+'">'+c.status+'</span></td><td>$'+c.mrr+'</td><td>'+c.orders_count+'</td><td style="color:var(--muted);font-size:12px">'+(c.last_login?c.last_login.slice(0,16):'—')+'</td></tr>';
}).join('');
}
async function loadOrders(){
const cs=await fetch('/customers').then(function(r){return r.json()});
const orders=[];
for(const c of cs){try{const os=await fetch('/customers/'+c.external_id+'/orders').then(function(r){return r.json()});os.forEach(function(o){o.customer_name=c.name});orders.push(...os)}catch(e){}}
document.getElementById('ordBody').innerHTML=orders.map(function(o){
return '<tr><td><strong>'+o.order_number+'</strong></td><td>'+o.customer_name+'</td><td><span class="pill '+pillClass(o.status)+'">'+o.status+'</span></td><td>$'+o.total+'</td><td>'+o.items.length+' item(s)</td><td style="color:var(--muted);font-size:12px">'+o.created_at.slice(0,10)+'</td></tr>';
}).join('');
}
load();
</script>
</body>
</html>"""


# ── Startup ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
