"""Agent Tools CRUD + execution log routes."""
from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .auth import get_current_tenant
from .db import get_db
from .models import AgentTool, AgentToolLog, Tenant
from .schemas import AgentToolIn, AgentToolOut, AgentToolLogOut

router = APIRouter(prefix="/tools", tags=["tools"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _fmt_url(url: str, params: dict[str, Any]) -> str:
    try:
        return url.format(**params)
    except KeyError:
        return url


def mask_headers(h: dict | None) -> dict:
    out = {}
    for k, v in (h or {}).items():
        if k.lower() in {"authorization", "x-api-key", "api-key", "token"}:
            out[k] = "********"
        else:
            out[k] = v
    return out


def merge_headers(existing: dict | None, incoming: dict | None) -> dict:
    merged = dict(existing or {})
    for k, v in (incoming or {}).items():
        if v == "********":
            continue
        if v == "":
            merged.pop(k, None)
        else:
            merged[k] = v
    return merged


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AgentToolOut])
def list_tools(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    rows = db.query(AgentTool).filter(AgentTool.tenant_id == tenant.id).order_by(AgentTool.created_at).all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=AgentToolOut, status_code=201)
def create_tool(body: AgentToolIn, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    _assert_unique_name(db, tenant.id, body.name)
    tool = AgentTool(
        tenant_id=tenant.id,
        name=body.name,
        description=body.description,
        tool_type=body.tool_type,
        method=body.method.upper(),
        url_template=body.url_template,
        headers=body.headers,
        body_template=body.body_template,
        parameters=body.parameters,
        require_confirmation=body.require_confirmation,
        enabled=body.enabled,
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return _to_out(tool)


@router.get("/{tool_id}", response_model=AgentToolOut)
def get_tool(tool_id: uuid.UUID, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    return _to_out(_get_or_404(db, tenant.id, tool_id))


@router.put("/{tool_id}", response_model=AgentToolOut)
def update_tool(
    tool_id: uuid.UUID,
    body: AgentToolIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    tool = _get_or_404(db, tenant.id, tool_id)
    if body.name != tool.name:
        _assert_unique_name(db, tenant.id, body.name)
    tool.name = body.name
    tool.description = body.description
    tool.tool_type = body.tool_type
    tool.method = body.method.upper()
    tool.url_template = body.url_template
    tool.headers = merge_headers(tool.headers, body.headers)
    tool.body_template = body.body_template
    tool.parameters = body.parameters
    tool.require_confirmation = body.require_confirmation
    tool.enabled = body.enabled
    db.commit()
    db.refresh(tool)
    return _to_out(tool)


@router.delete("/{tool_id}", status_code=204)
def delete_tool(tool_id: uuid.UUID, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    tool = _get_or_404(db, tenant.id, tool_id)
    db.delete(tool)
    db.commit()


@router.post("/{tool_id}/test")
async def test_tool(
    tool_id: uuid.UUID,
    body: dict = {},
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Execute the tool with provided params and return raw response."""
    tool = _get_or_404(db, tenant.id, tool_id)
    started = time.perf_counter()
    try:
        result = await _call_tool(tool, params=body, user_id="test")
        return {"ok": True, "latency_ms": int((time.perf_counter() - started) * 1000), "response": result}
    except Exception as e:
        return {"ok": False, "latency_ms": int((time.perf_counter() - started) * 1000), "error": str(e)}


@router.get("/{tool_id}/logs", response_model=list[AgentToolLogOut])
def tool_logs(
    tool_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    _get_or_404(db, tenant.id, tool_id)
    rows = (
        db.query(AgentToolLog)
        .filter(AgentToolLog.tool_id == tool_id)
        .order_by(AgentToolLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_log_to_out(r) for r in rows]


@router.get("/logs/recent", response_model=list[AgentToolLogOut])
def recent_logs(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    limit: int = 100,
):
    rows = (
        db.query(AgentToolLog)
        .filter(AgentToolLog.tenant_id == tenant.id)
        .order_by(AgentToolLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_log_to_out(r) for r in rows]


# ── internal helpers used by agent ───────────────────────────────────────────

def get_enabled_tools(db: Session, tenant_id: uuid.UUID) -> list[AgentTool]:
    return (
        db.query(AgentTool)
        .filter(AgentTool.tenant_id == tenant_id, AgentTool.enabled == True)  # noqa: E712
        .order_by(AgentTool.created_at)
        .all()
    )


def build_tool_schemas(tools: list[AgentTool]) -> list[dict]:
    """Convert AgentTool rows to OpenAI function-calling schemas."""
    schemas = []
    for t in tools:
        params = dict(t.parameters or {})
        # Always inject user_id so agent can pass it for URL templating
        props = params.get("properties", {})
        if "user_id" not in props:
            props["user_id"] = {"type": "string", "description": "The customer's user identifier"}
        params["properties"] = props
        params.setdefault("type", "object")
        params.setdefault("required", [])

        desc = t.description
        if t.tool_type == "action" and t.require_confirmation:
            desc += "\nIMPORTANT: Before calling this tool, summarize the action to the user and get explicit confirmation. Only proceed when confirmed."

        schemas.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": desc,
                "parameters": params,
            },
        })
    return schemas


async def dispatch_tool(
    db: Session,
    tenant_id: uuid.UUID,
    tool: AgentTool,
    args: dict[str, Any],
    user_id: str,
) -> dict:
    """Call the tool HTTP endpoint and log the result."""
    started = time.perf_counter()
    status = "ok"
    response = None
    error = None
    try:
        response = await _call_tool(tool, params=args, user_id=user_id)
    except Exception as e:
        status = "failed"
        error = str(e)
        response = {"error": error}
    finally:
        latency = int((time.perf_counter() - started) * 1000)
        db.add(AgentToolLog(
            tenant_id=tenant_id,
            tool_id=tool.id,
            tool_name=tool.name,
            user_id=user_id,
            status=status,
            request={k: v for k, v in args.items()},
            response=response,
            error=error,
            latency_ms=latency,
        ))
        db.commit()
    return response


async def _call_tool(tool: AgentTool, params: dict[str, Any], user_id: str) -> Any:
    url = _fmt_url(tool.url_template, {**params, "user_id": user_id})
    headers = dict(tool.headers or {})
    body = dict(tool.body_template or {})
    # Merge dynamic params into body for non-GET requests
    if tool.method != "GET":
        body.update({k: v for k, v in params.items() if k != "user_id"})

    async with httpx.AsyncClient(timeout=15.0) as client:
        if tool.method == "GET":
            r = await client.get(url, headers=headers)
        elif tool.method == "POST":
            r = await client.post(url, json=body, headers=headers)
        elif tool.method == "PATCH":
            r = await client.patch(url, json=body, headers=headers)
        elif tool.method == "PUT":
            r = await client.put(url, json=body, headers=headers)
        elif tool.method == "DELETE":
            r = await client.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {tool.method}")
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        return r.json() if "json" in ct else {"text": r.text[:2000]}


# ── private ───────────────────────────────────────────────────────────────────

def _get_or_404(db: Session, tenant_id: uuid.UUID, tool_id: uuid.UUID) -> AgentTool:
    t = db.query(AgentTool).filter(AgentTool.id == tool_id, AgentTool.tenant_id == tenant_id).first()
    if not t:
        raise HTTPException(404, "Tool not found")
    return t


def _assert_unique_name(db: Session, tenant_id: uuid.UUID, name: str) -> None:
    exists = db.query(AgentTool).filter(AgentTool.tenant_id == tenant_id, AgentTool.name == name).first()
    if exists:
        raise HTTPException(400, f"Tool name '{name}' already exists")


def _to_out(t: AgentTool) -> AgentToolOut:
    return AgentToolOut(
        id=t.id,
        name=t.name,
        description=t.description,
        tool_type=t.tool_type,
        method=t.method,
        url_template=t.url_template,
        headers=mask_headers(t.headers),
        body_template=t.body_template or {},
        parameters=t.parameters or {},
        require_confirmation=t.require_confirmation,
        enabled=t.enabled,
        created_at=t.created_at.isoformat(),
    )


def _log_to_out(r: AgentToolLog) -> AgentToolLogOut:
    return AgentToolLogOut(
        id=r.id,
        tool_name=r.tool_name,
        user_id=r.user_id,
        status=r.status,
        request=r.request,
        response=r.response,
        error=r.error,
        latency_ms=r.latency_ms,
        created_at=r.created_at.isoformat(),
    )
