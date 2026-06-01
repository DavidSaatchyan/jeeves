from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Appointment, AppointmentCache, CrmConnection, Provider, Tenant
from .deps import get_admin_tenant
from .router import router


class _CreateAppointmentBody(BaseModel):
    patient_id: UUID
    provider_name: str
    start_time: datetime
    end_time: datetime
    reason: str | None = None
    source: str = "admin"


class _UpdateAppointmentBody(BaseModel):
    status: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    provider_name: str | None = None
    notes: str | None = None
    reason: str | None = None


class _CancelAppointmentBody(BaseModel):
    reason: str | None = None


APPOINTMENT_STATUSES = {
    "scheduled", "confirmed", "arrived", "in_progress",
    "completed", "cancelled", "no_show", "rescheduled",
}


def _has_crm(tenant_id: UUID, db: Session) -> bool:
    return db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant_id,
        CrmConnection.status == "connected",
    ).first() is not None


def _get_crm_adapter(tenant_id: UUID, db: Session):
    conn = db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant_id,
        CrmConnection.status == "connected",
    ).first()
    if not conn:
        return None
    from ..integrations.crm import get_crm_adapter
    return get_crm_adapter(conn.provider, conn.config)


def _normalize_crm_appointment(data: dict) -> dict:
    return {
        "id": str(data.get("id", "")),
        "patient_id": str(data.get("patient_id", "")),
        "external_id": str(data.get("external_id", "")),
        "provider_name": data.get("provider_name", ""),
        "provider_specialty": data.get("provider_specialty"),
        "department": data.get("department"),
        "start_time": data.get("start_time"),
        "end_time": data.get("end_time"),
        "status": data.get("status", "scheduled"),
        "reason": data.get("reason"),
        "notes": data.get("notes"),
        "source": "crm_sync",
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }


@router.get("/api/appointments")
def list_appointments(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    provider: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    patient_id: UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        result = adapter.list_appointments(
            tenant_id=str(tenant.id),
            status=status,
            provider=provider,
            date_from=date_from,
            date_to=date_to,
            patient_id=str(patient_id) if patient_id else None,
            offset=offset,
            limit=limit,
        )
        items = result.get("items", result.get("appointments", []))
        return {
            "total": result.get("total", len(items)),
            "offset": offset,
            "limit": limit,
            "appointments": [_normalize_crm_appointment(item) for item in items],
        }

    q = select(Appointment).where(Appointment.tenant_id == tenant.id)

    if status:
        q = q.where(Appointment.status == status)
    if provider:
        q = q.where(Appointment.provider_name == provider)
    if patient_id:
        q = q.where(Appointment.patient_id == patient_id)
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from)
            q = q.where(Appointment.start_time >= dt)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to)
            q = q.where(Appointment.start_time <= dt)
        except ValueError:
            pass

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    rows = db.execute(q.order_by(Appointment.start_time).offset(offset).limit(limit)).scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "appointments": [_appt_to_dict(a) for a in rows],
    }


@router.get("/api/appointments/slots")
def available_slots(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    provider_name: str | None = Query(None),
    specialty: str | None = Query(None),
    date_str: str | None = Query(None, alias="date"),
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        target_date = date.today().isoformat()
        if date_str:
            try:
                target_date = date.fromisoformat(date_str).isoformat()
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid date format (use YYYY-MM-DD)")
        crm_slots = adapter.search_available_slots(
            doctor_id=provider_name or "",
            date=target_date,
        )
        return {
            "slots": [
                {
                    "start": s.get("start_time", s.get("start", "")),
                    "end": s.get("end_time", s.get("end", "")),
                    "provider_name": s.get("provider_name", provider_name or ""),
                    "provider_specialty": s.get("provider_specialty"),
                    "slot_token": s.get("slot_token", ""),
                }
                for s in (crm_slots if isinstance(crm_slots, list) else [])
            ],
        }

    from ..core.booking import get_available_slots

    target = None
    if date_str:
        try:
            target = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format (use YYYY-MM-DD)")

    slots = get_available_slots(
        db, tenant.id,
        provider_name=provider_name,
        specialty=specialty,
        day=target,
    )
    return {
        "slots": [
            {
                "start": s.start.isoformat(),
                "end": s.end.isoformat(),
                "provider_name": s.provider_name,
                "provider_specialty": s.provider_specialty,
                "slot_token": s.slot_token,
            }
            for s in slots
        ],
    }


@router.get("/api/appointments/{appointment_id}")
def get_appointment(
    appointment_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        cache = db.execute(
            select(AppointmentCache).where(
                AppointmentCache.id == appointment_id,
                AppointmentCache.tenant_id == tenant.id,
            )
        ).scalar_one_or_none()
        if not cache or not cache.external_id:
            raise HTTPException(status_code=404, detail="Appointment not found")
        result = adapter.get_appointment(cache.external_id)
        if not result:
            raise HTTPException(status_code=404, detail="Appointment not found in CRM")
        return _normalize_crm_appointment(result)

    appt = db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.tenant_id == tenant.id,
        )
    ).scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return _appt_to_dict(appt)


@router.post("/api/appointments")
def create_appointment(
    body: _CreateAppointmentBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        crm_result = adapter.create_appointment(
            patient_id=str(body.patient_id),
            data={
                "provider_name": body.provider_name,
                "start_time": body.start_time.isoformat(),
                "end_time": body.end_time.isoformat(),
                "reason": body.reason,
                "source": body.source,
            },
        )
        cache = AppointmentCache(
            tenant_id=tenant.id,
            patient_id=body.patient_id,
            external_id=str(crm_result.get("id", "")),
            status="scheduled",
            source=body.source,
        )
        db.add(cache)
        db.commit()
        return _normalize_crm_appointment(crm_result)

    from ..core.booking import book_appointment

    try:
        appt = book_appointment(
            db=db,
            tenant_id=tenant.id,
            patient_id=body.patient_id,
            slot_token="",
            provider_name=body.provider_name,
            start_time=body.start_time,
            end_time=body.end_time,
            reason=body.reason,
            source=body.source,
        )
        db.commit()
        return _appt_to_dict(appt)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/api/appointments/{appointment_id}")
def update_appointment(
    appointment_id: UUID,
    body: _UpdateAppointmentBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        cache = db.get(AppointmentCache, appointment_id)
        if not cache:
            raise HTTPException(status_code=404, detail="Appointment not found")
        update_data = body.model_dump(exclude_none=True)
        if update_data:
            adapter.update_appointment(cache.external_id, update_data)
        if body.status:
            cache.status = body.status
        cache.updated_at = datetime.utcnow()
        db.commit()
        return _normalize_crm_appointment({
            "id": cache.external_id,
            "patient_id": str(cache.patient_id),
            "external_id": cache.external_id,
            "status": cache.status,
            "source": cache.source,
            "updated_at": cache.updated_at.isoformat() if cache.updated_at else None,
        })

    appt = db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.tenant_id == tenant.id,
        )
    ).scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if body.status is not None:
        if body.status not in APPOINTMENT_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status: {body.status}")
        appt.status = body.status
    if body.start_time is not None:
        appt.start_time = body.start_time
    if body.end_time is not None:
        appt.end_time = body.end_time
    if body.provider_name is not None:
        appt.provider_name = body.provider_name
    if body.notes is not None:
        appt.notes = body.notes
    if body.reason is not None:
        appt.reason = body.reason

    db.commit()
    return _appt_to_dict(appt)


@router.post("/api/appointments/{appointment_id}/cancel")
def cancel_appointment_endpoint(
    appointment_id: UUID,
    body: _CancelAppointmentBody = _CancelAppointmentBody(),
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        cache = db.get(AppointmentCache, appointment_id)
        if not cache:
            raise HTTPException(status_code=404, detail="Appointment not found")
        adapter.cancel_appointment(cache.external_id)
        cache.status = "cancelled"
        cache.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": True}

    from ..core.booking import cancel_appointment

    ok = cancel_appointment(db, appointment_id, reason=body.reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Appointment not found")
    db.commit()
    return {"ok": True}


@router.get("/api/providers")
def list_providers(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    specialty: str | None = Query(None),
):
    q = select(Provider).where(Provider.tenant_id == tenant.id)
    if specialty:
        q = q.where(Provider.specialty == specialty)
    rows = db.execute(q.order_by(Provider.name)).scalars().all()
    return {
        "providers": [
            {
                "id": str(p.id),
                "name": p.name,
                "specialty": p.specialty,
                "email": p.email,
                "phone": p.phone,
                "has_schedule": bool(p.schedule),
            }
            for p in rows
        ],
    }


def _appt_to_dict(a: Appointment) -> dict:
    return {
        "id": str(a.id),
        "tenant_id": str(a.tenant_id),
        "patient_id": str(a.patient_id),
        "external_id": a.external_id,
        "provider_name": a.provider_name,
        "provider_specialty": a.provider_specialty,
        "department": a.department,
        "start_time": a.start_time.isoformat() if a.start_time else None,
        "end_time": a.end_time.isoformat() if a.end_time else None,
        "status": a.status,
        "reason": a.reason,
        "notes": a.notes,
        "source": a.source,
        "reminder_sent_24h": a.reminder_sent_24h,
        "reminder_sent_2h": a.reminder_sent_2h,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }
