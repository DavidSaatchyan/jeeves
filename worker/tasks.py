"""Celery tasks: RAG indexing + proactive engine.

The worker talks to the same Postgres/Redis/Chroma as the API. The indexing
path mirrors api/app/rag.py so the worker is self-contained and doesn't
need to import the FastAPI app.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import chromadb
import httpx
import yaml
from celery import Celery
from celery.schedules import crontab
from jsonpath_ng.ext import parse as jp_parse
from openai import OpenAI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import chunking

# --- config ---------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg2://jeeves:jeeves123@postgres:5432/jeeves")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CHROMA_URL = os.environ.get("CHROMA_URL", "http://chroma:8000")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config.yaml")

_cfg: dict[str, Any] = {}
if Path(CONFIG_PATH).exists():
    _cfg = yaml.safe_load(Path(CONFIG_PATH).read_text(encoding="utf-8")) or {}
_rag = _cfg.get("rag", {})
CHUNK_SIZE = int(_rag.get("chunk_size", 512))
CHUNK_OVERLAP = int(_rag.get("chunk_overlap", 64))
EMBED_MODEL = _rag.get("embedding_model", "text-embedding-3-small")
EMBEDDING_VERSION = f"{EMBED_MODEL}:v1"
_proactive = _cfg.get("proactive", {})
MIN_DAYS_BETWEEN = int(_proactive.get("min_days_between_trigger", 3))
DEFAULT_THRESHOLD = int(_proactive.get("default_threshold_percent", 30))

_CHUNK_CHARS = CHUNK_SIZE * 4
_OVERLAP_CHARS = CHUNK_OVERLAP * 4

# --- celery app -----------------------------------------------------------
app = Celery("jeeves", broker=REDIS_URL, backend=REDIS_URL)
app.conf.update(task_serializer="json", accept_content=["json"], timezone="UTC")
app.conf.beat_schedule = {
    # DEFAULT: check proactive triggers every hour.
    "proactive-hourly": {
        "task": "tasks.run_proactive",
        "schedule": crontab(minute=0),
    },
}

# --- shared clients -------------------------------------------------------
_engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=_engine, future=True)


def _openai() -> OpenAI:
    return OpenAI(api_key=OPENAI_API_KEY)


def _chroma():
    u = urlparse(CHROMA_URL)
    return chromadb.HttpClient(host=u.hostname or "chroma", port=u.port or 8000)


def _collection(tenant_id: str):
    return _chroma().get_or_create_collection(
        name=f"tenant_{tenant_id.replace('-', '')}",
        metadata={"hnsw:space": "cosine", "embedding_version": EMBEDDING_VERSION},
    )


# --- helpers --------------------------------------------------------------
def _extract(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    raise ValueError(f"unsupported ext {ext}")


def _chunk(text_: str) -> list[str]:
    text_ = text_.strip()
    if not text_:
        return []
    out, i, step = [], 0, max(1, _CHUNK_CHARS - _OVERLAP_CHARS)
    while i < len(text_):
        out.append(text_[i : i + _CHUNK_CHARS])
        i += step
    return out


def _embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    r = _openai().embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in r.data]


# --- tasks ----------------------------------------------------------------
@app.task(name="tasks.index_file", bind=True, max_retries=3, default_retry_delay=10)
def index_file(self, tenant_id: str, file_id: str, path: str) -> dict:
    """Extract → chunk → embed → store in Chroma; update files.status."""
    db = SessionLocal()
    try:
        try:
            chunks = chunking.build_chunks(Path(path))
            col = _collection(tenant_id)
            try:
                col.delete(where={"file_id": file_id})
            except Exception:
                pass
            if chunks:
                chunk_texts = [c.text for c in chunks]
                embs = _embed(chunk_texts)
                col.add(
                    ids=[f"{file_id}-{i}-{c.chunk_hash}" for i, c in enumerate(chunks)],
                    embeddings=embs,
                    documents=chunk_texts,
                    metadatas=[c.to_metadata(file_id) for c in chunks],
                )
            db.execute(
                text(
                    """
                    UPDATE files
                    SET status='ready', chunks_total=:chunks_total, error=NULL
                    WHERE id=:fid
                    """
                ),
                {"fid": file_id, "chunks_total": len(chunks)},
            )
            db.commit()
            return {"ok": True, "chunks": len(chunks)}
        except Exception as e:
            db.execute(
                text("UPDATE files SET status='failed', error=:error WHERE id=:fid"),
                {"fid": file_id, "error": str(e)[:2000]},
            )
            db.commit()
            print(f"[worker] index_file failed: {e}", flush=True)
            raise
    finally:
        db.close()


def _dropped_enough(series: list[float], threshold_pct: int) -> bool:
    """Check if the most-recent value is threshold_pct% lower than the 3-day baseline."""
    if not series or len(series) < 4:
        return False
    recent = series[-1]
    baseline = sum(series[-4:-1]) / 3 if len(series) >= 4 else sum(series[:-1]) / max(1, len(series) - 1)
    if baseline <= 0:
        return False
    drop = (baseline - recent) / baseline * 100
    return drop >= threshold_pct


def _extract_series(payload: Any) -> list[float]:
    """Extract a numeric time-series from a CRM-activity response.

    DEFAULT heuristic: look for `$.data.series[*]` or `$.series[*]` of numbers,
    else flatten any list of numbers at top level.
    """
    for expr in ("$.data.series[*]", "$.series[*]", "$.data.activity[*]", "$.activity[*]"):
        try:
            vals = [m.value for m in jp_parse(expr).find(payload)]
            vals = [float(v) for v in vals if isinstance(v, (int, float))]
            if vals:
                return vals
        except Exception:
            continue
    if isinstance(payload, list) and all(isinstance(x, (int, float)) for x in payload):
        return [float(x) for x in payload]
    return []


@app.task(name="tasks.run_proactive")
def run_proactive() -> dict:
    """Iterate tenants, fetch metric per known user, trigger proactive message on drop."""
    db = SessionLocal()
    triggered = 0
    try:
        # Fetch tenants that configured proactive metric AND have a CRM write/read URL to know users.
        rows = db.execute(
            text(
                """
                SELECT pm.tenant_id, pm.metric_url, pm.threshold, pm.last_triggered_per_user, cc.headers
                FROM proactive_metric pm
                LEFT JOIN crm_config cc ON cc.tenant_id = pm.tenant_id
                WHERE pm.metric_url IS NOT NULL AND pm.metric_url <> ''
                """
            )
        ).fetchall()

        for r in rows:
            tenant_id = str(r.tenant_id)
            metric_url = r.metric_url
            threshold = int(r.threshold or DEFAULT_THRESHOLD)
            last_map = r.last_triggered_per_user or {}
            headers = r.headers or {}

            # Collect recent user_ids from chat_logs for this tenant (anyone who talked to us).
            user_rows = db.execute(
                text(
                    "SELECT DISTINCT user_id FROM chat_logs WHERE tenant_id=:t AND created_at >= :since"
                ),
                {"t": r.tenant_id, "since": datetime.utcnow() - timedelta(days=30)},
            ).fetchall()

            for (user_id,) in user_rows:
                # throttle
                last_iso = last_map.get(user_id)
                if last_iso:
                    try:
                        last_dt = datetime.fromisoformat(last_iso)
                        if datetime.utcnow() - last_dt < timedelta(days=MIN_DAYS_BETWEEN):
                            continue
                    except Exception:
                        pass

                url = metric_url.replace("{id}", user_id).replace("{user_id}", user_id)
                try:
                    with httpx.Client(timeout=10.0) as c:
                        resp = c.get(url, headers=headers)
                    if resp.status_code >= 400:
                        continue
                    payload = resp.json()
                except Exception as e:
                    print(f"[proactive] metric fetch failed for {user_id}: {e}", flush=True)
                    continue

                series = _extract_series(payload)
                if not _dropped_enough(series, threshold):
                    continue

                # Persist outgoing message → widget inbox will deliver it.
                msg = "Hi! I noticed your activity dropped recently. Need any help?"
                db.execute(
                    text(
                        """
                        INSERT INTO chat_logs (id, tenant_id, user_id, direction, message, response, resolution, delivered, created_at)
                        VALUES (:id, :t, :u, 'outgoing', NULL, :m, 'resolved', false, :ts)
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "t": r.tenant_id,
                        "u": user_id,
                        "m": msg,
                        "ts": datetime.utcnow(),
                    },
                )
                last_map[user_id] = datetime.utcnow().isoformat()
                triggered += 1

            db.execute(
                text("UPDATE proactive_metric SET last_triggered_per_user=:m WHERE tenant_id=:t"),
                {"m": json.dumps(last_map), "t": r.tenant_id},
            )
            db.commit()
        return {"triggered": triggered}
    finally:
        db.close()


# --- outgoing webhooks (Task 9) -------------------------------------------

def _get_outgoing_secret_plain(db) -> dict:
    """Load decrypted outgoing webhook secrets for all tenants."""
    rows = db.execute(
        text(
            """
            SELECT tenant_id, outgoing_url, outgoing_secret, events
            FROM webhook_configs
            WHERE outgoing_url IS NOT NULL AND outgoing_url <> '' AND enabled = true
            """
        )
    ).fetchall()
    result = {}
    for r in rows:
        secret_plain = ""
        if r.outgoing_secret:
            try:
                from sqlalchemy import text as _t
                from cryptography.fernet import Fernet, InvalidToken
                import os
                fernet_key = os.environ.get("FERNET_KEY", "")
                if fernet_key:
                    f = Fernet(fernet_key.encode())
                    secret_plain = f.decrypt(r.outgoing_secret.encode()).decode()
            except Exception:
                pass
        result[str(r.tenant_id)] = {
            "url": r.outgoing_url,
            "secret": secret_plain,
            "events": r.events or [],
        }
    return result


@app.task(
    name="tasks.send_outgoing_webhook",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def send_outgoing_webhook(self, tenant_id: str, event: str, payload: dict) -> dict:
    """POST to configured outgoing_url with HMAC-SHA256 signature.

    Retry 3x with exponential backoff (10s, 30s, 90s).
    Log failure to agent_tool_logs after all retries exhausted.
    """
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT outgoing_url, outgoing_secret, events
                FROM webhook_configs
                WHERE tenant_id=:tid AND enabled = true
                """
            ),
            {"tid": tenant_id},
        ).fetchone()

        if not row or not row.outgoing_url:
            return {"skipped": True, "reason": "no outgoing webhook config"}

        events = row.events or []
        if event not in events:
            return {"skipped": True, "reason": f"event {event} not in config events"}

        secret_plain = ""
        if row.outgoing_secret:
            try:
                from cryptography.fernet import Fernet
                import os
                fernet_key = os.environ.get("FERNET_KEY", "")
                if fernet_key:
                    f = Fernet(fernet_key.encode())
                    secret_plain = f.decrypt(row.outgoing_secret.encode()).decode()
            except Exception:
                pass

        body = json.dumps(payload, ensure_ascii=False, default=str)
        headers = {"Content-Type": "application/json"}
        if secret_plain:
            import hashlib
            import hmac as _hmac
            sig = _hmac.new(
                secret_plain.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Jeeves-Signature"] = f"sha256={sig}"

        try:
            with httpx.Client(timeout=10.0) as c:
                resp = c.post(row.outgoing_url, content=body, headers=headers)
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            return {"ok": True, "status_code": resp.status_code}
        except Exception as e:
            if self.retries < self.max_retries:
                delay = 10 * (3 ** self.retries)  # 10, 30, 90
                raise self.retry(exc=e, countdown=delay)
            # Log failure
            db.execute(
                text(
                    """
                    INSERT INTO agent_tool_logs (id, tenant_id, tool_name, user_id, status, request, error, latency_ms, created_at)
                    VALUES (:id, :tid, 'send_outgoing_webhook', :uid, 'failed', :req, :err, NULL, :ts)
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "uid": payload.get("user_id", ""),
                    "req": {"event": event, **payload},
                    "err": str(e)[:2000],
                    "ts": datetime.utcnow(),
                },
            )
            db.commit()
            return {"ok": False, "error": str(e)}
    finally:
        db.close()


# --- write-back (Task 10) -------------------------------------------------

@app.task(
    name="tasks.writeback_conversation",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def writeback_conversation(self, tenant_id: str, session_id: str) -> dict:
    """Generate conversation summary and write back to CRM or webhook.

    type=off: return immediately
    type=hubspot_note: call HubSpot note creation API
    type=webhook: POST summary to configured webhook_url
    """
    db = SessionLocal()
    try:
        wbc = db.execute(
            text(
                """
                SELECT type, hubspot_note_enabled, hubspot_task_on_escalation, webhook_url
                FROM writeback_configs
                WHERE tenant_id=:tid
                """
            ),
            {"tid": tenant_id},
        ).fetchone()

        if not wbc or wbc.type == "off":
            return {"skipped": True, "reason": "writeback disabled"}

        # Gather conversation turns for this session
        turns = db.execute(
            text(
                """
                SELECT message, response, action_called, resolution
                FROM chat_logs
                WHERE tenant_id=:tid AND session_id=:sid
                ORDER BY created_at ASC
                """
            ),
            {"tid": tenant_id, "sid": session_id},
        ).fetchall()

        if not turns:
            return {"skipped": True, "reason": "no turns found"}

        # Build summary using OpenAI
        conversation_text = "\n".join(
            f"User: {t.message}\nAgent: {t.response}"
            for t in turns if t.message or t.response
        )
        summary_prompt = (
            "Summarize this customer support conversation in 3-5 sentences. "
            "Include the main issue, resolution status, and any actions taken.\n\n"
            f"{conversation_text}"
        )

        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are a conversation summarizer."},
                      {"role": "user", "content": summary_prompt}],
            temperature=0.2,
        )
        summary = resp.choices[0].message.content or ""

        write_type = wbc.type

        if write_type == "hubspot_note" or (write_type == "webhook" and wbc.hubspot_note_enabled):
            # Call HubSpot note creation — use internal API endpoint
            last_turn = turns[-1]
            user_id = last_turn[0] if last_turn[0] else ""
            try:
                from sqlalchemy import text as _t2
                api_url = os.environ.get("API_INTERNAL_URL", "http://api:8000")
                with httpx.Client(timeout=15.0) as c:
                    c.post(
                        f"{api_url}/crm/note",
                        json={
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                            "note": summary,
                        },
                    )
            except Exception as e:
                print(f"[writeback] hubspot note failed: {e}", flush=True)

        if write_type == "webhook" and wbc.webhook_url:
            try:
                with httpx.Client(timeout=10.0) as c:
                    c.post(
                        wbc.webhook_url,
                        json={
                            "tenant_id": tenant_id,
                            "session_id": session_id,
                            "summary": summary,
                            "escalated": any(t.resolution == "escalated" for t in turns),
                        },
                    )
            except Exception as e:
                if self.retries < self.max_retries:
                    delay = 10 * (3 ** self.retries)
                    raise self.retry(exc=e, countdown=delay)
                print(f"[writeback] webhook POST failed: {e}", flush=True)

        return {"ok": True, "summary": summary[:200], "type": write_type}
    finally:
        db.close()
