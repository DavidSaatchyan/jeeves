# WhatsApp Channel: Implementation Plan

**Цель:** Дать клиникам (эстетическая медицина, Европа) возможность подключать WhatsApp в админке в 2 клика — без копания в Meta Dashboard, без BSP-посредников, с GDPR-комплаенсом из коробки.

**Принцип:** Двухслойная архитектура — Twilio для dev/CI, Meta Cloud API для production. Общий абстрактный интерфейс, переключение провайдера на уровне tenant.

---

## Содержание

1. [Архитектура](#1-архитектура)
2. [Фаза 0 — Twilio Sandbox Adapter (dev ready)](#2-фаза-0--twilio-sandbox-adapter-dev-ready)
3. [Фаза 1 — Abstract Channel Interface (Meta Channels)](#3-фаза-1--abstract-channel-interface-meta-channels)
4. [Фаза 2 — WhatsApp Embedded Signup (production)](#4-фаза-2--whatsapp-embedded-signup-production)
5. [Фаза 3 — Provider Routing & Admin UI](#5-фаза-3--provider-routing--admin-ui)
6. [Фаза 4 — Instagram-Specific Optimizations](#6-фаза-4--instagram-specific-optimizations--shared-fixes)
7. [UX/UI Design & Scenarios](#7-uxui-design--scenarios)
8. [Testing Strategy](#8-testing-strategy)
9. [GDPR / Compliance](#9-gdpr--compliance)
10. [Files & Dependencies](#10-files--dependencies)
11. [Rollback](#11-rollback)
12. [Instagram Optimization — Audit Findings](#12-instagram-optimization--audit-findings)
13. [Dependency Graph (Optimized)](#13-dependency-graph-optimized)
14. [Time Estimate (Optimized)](#14-time-estimate-optimized)
15. [Critical Review & Optimization](#15-critical-review--optimization)

---

## 1. Архитектура

```
┌─ Inbound ──────────────────────────────────────────────────┐
│                                                             │
│  Twilio Webhook          Meta Cloud API Webhook             │
│  POST /channels/twilio   POST /channels/whatsapp/webhook    │
│         │                         │                         │
│         └─────────┬───────────────┘                         │
│                   ▼                                         │
│         channels/router.py                                   │
│         resolve_tenant → provider → send_message()          │
│                   │                                         │
│                   ▼                                         │
│         channels/whatsapp.py  (send, receive)               │
│         channels/twilio.py    (send, receive)               │
│                   │                                         │
│                   ▼                                         │
│         agents/service.py → process_message()               │
│         core/workflows/ → route_event()                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─ Outbound ─────────────────────────────────────────────────┐
│                                                             │
│  send_message(tenant_id, recipient, text)                   │
│       │                                                     │
│       ▼                                                     │
│  channels/router.py → get_adapter(provider)                 │
│       │                                                     │
│       ├─ TwilioAdapter    → messages.create()               │
│       └─ MetaAdapter      → POST Cloud API                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─ Onboarding ───────────────────────────────────────────────┐
│                                                             │
│  Admin Panel → GET /whatsapp/auth → Meta OAuth              │
│                                    → callback → token       │
│                                    → webhook subscribe      │
│                                    → channel active         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Provider-agnostic routing

Ключевое решение: **не разделять tenants по разным endpoint'ам**. Единый вебхук `/channels/whatsapp/webhook` (и новый `/channels/twilio/webhook` для dev), но роутинг определяется конфигом tenant'а:

| Tenant | provider в ChannelConfig | Используемый адаптер |
|--------|------------------------|---------------------|
| Clinic A | `meta` | WhatsApp Cloud API |
| Clinic B | `twilio_dev` | Twilio (dev/small) |

---

## 2. Фаза 0 — Twilio Sandbox Adapter (dev ready)

**Зачем:** Разработка и тестирование без Meta. Twilio Sandbox работает с любым номером, не требует верификации.

### 2.1 `api/app/channels/twilio.py` — новый файл

```python
"""Twilio WhatsApp Sandbox channel — dev/CI only, no Meta needed."""

TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

router = APIRouter(prefix="/channels/twilio", tags=["twilio"])

# ── Config format (ChannelConfig.config) ──
# {
#   "account_sid": "ACxxx",
#   "auth_token": "xxx",
#   "twilio_phone_number": "+14155238886",  # sandbox number
#   "provider": "twilio_dev"
# }

def _resolve_tenant(db, twilio_to: str) -> tuple[Tenant | None, ChannelConfig | None]:
    """Resolve tenant by the Twilio 'To' number (their sandbox number)."""
    ...

async def _send_message(account_sid, auth_token, from_, to, text) -> dict:
    """Send via Twilio Messages API (basic auth)."""
    auth = httpx.BasicAuth(account_sid, auth_token)
    r = await client.post(url, auth=auth, data={...})
    ...

@router.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    """Twilio incoming webhook (form-encoded)."""
    form = await request.form()
    # Twilio sends: From, To, Body, MessageSid, SmsStatus, ...
    wa_id = form["From"]       # e.g. "whatsapp:+1234567890"
    text = form["Body"]
    tenant, config = _resolve_tenant(db, form["To"])
    if not tenant: return Response("", status_code=404)
    result = await process_message(tenant.id, config, wa_id, text, channel="twilio")
    return Response("", status_code=200)
```

### 2.2 Admin endpoint — `integrations_hub.py`

```python
@router.post("/api/integrations/twilio/configure")
def configure_twilio(body: _TwilioConfigureBody, ...):
    upsert_channel(db, tenant.id, "twilio_dev", config, status="active")
    return {"ok": True}
```

### 2.3 Тестирование

```
# В любом WhatsApp → отправить "join <sandbox-code>" на +1 415 523 8886
# → Twilio шлёт POST на /channels/twilio/webhook
# → process_message → ответ
```

**Проверка:**
```bash
pytest api/tests/ -v --tb=short -k "twilio or whatsapp"
python -c "from app.channels.twilio import router; print('OK')"
```

**Оценка:** 4-6 часов. Файл ~150 строк, знакомый паттерн (копия whatsapp.py с Twilio-спецификой).

---

## 3. Фаза 1 — Abstract Channel Interface (Meta Channels)

**Зачем:** Единый контракт для всех Meta-каналов. Сейчас `whatsapp.py` и `instagram.py` — независимые роутеры с дублированием логики (оба парсят Meta webhook, оба шлют в Graph API, оба резолвят tenant). Нужен базовый класс + общий MetaGraphClient.

### 3.1 `api/app/channels/base.py`

```python
class ChannelAdapter(ABC):
    provider: str  # "meta", "twilio_dev"
    channel_type: str  # "whatsapp", "instagram"

    @abstractmethod
    async def send_message(
        self, config: dict, recipient_id: str, text: str
    ) -> SendResult: ...

    @abstractmethod
    def parse_webhook(self, payload: Any) -> IncomingMessage | None: ...

    @abstractmethod
    def validate_config(self, config: dict) -> str | None:
        """Return error string or None if valid.""" ...

    @abstractmethod
    async def verify_webhook(self, request: Request) -> bool | str:
        """Return challenge string (GET) or True for POST verification.""" ...
```

### 3.2 `api/app/channels/meta_client.py` — общий Graph API клиент

```python
class MetaGraphClient:
    """Shared Graph API v22.0 client for all Meta channels."""

    API_VERSION = "v22.0"
    BASE = f"https://graph.facebook.com/{API_VERSION}"

    def __init__(self, access_token: str, timeout: float = 15.0):
        self.token = access_token
        self.timeout = timeout

    async def post(self, path: str, data: dict | None = None) -> dict: ...
    async def get(self, path: str, params: dict | None = None) -> dict: ...
    async def exchange_code(self, code: str, redirect_uri: str) -> str:
        """Code → access token (OAuth)."""
    async def get_long_lived_token(self, short_token: str) -> str:
        """60-day extension."""
```

Убирает дублирование: `channels/whatsapp.py`, `channels/instagram.py`, и `integrations/instagram.py` — все сейчас имеют свои копии Graph API URL и timeout.

### 3.3 Конкретные реализации

```python
class MetaWhatsAppAdapter(ChannelAdapter):
    provider = "meta"
    channel_type = "whatsapp"
    async def send_message(self, config, recipient_id, text) -> SendResult:
        # POST /{phone_number_id}/messages
    def parse_webhook(self, payload) -> IncomingMessage | None:
        # entry[].changes[].value.messages[]

class MetaInstagramAdapter(ChannelAdapter):
    provider = "meta"
    channel_type = "instagram"
    async def send_message(self, config, recipient_id, text) -> SendResult:
        # POST /{ig_account_id}/messages
    def parse_webhook(self, payload) -> IncomingMessage | None:
        # entry[].messaging[].message

class TwilioAdapter(ChannelAdapter):
    provider = "twilio_dev"
    channel_type = "whatsapp"
    async def send_message(self, config, recipient_id, text) -> SendResult:
        # Twilio Messages API
    def parse_webhook(self, form_data) -> IncomingMessage | None:
        # Twilio form-encoded → IncomingMessage
```

### 3.4 Рефакторинг `whatsapp.py` и `instagram.py`

Оба роутера после рефакторинга становятся тонкими (~80 строк):

```python
# whatsapp.py после рефакторинга (~80 строк вместо 253)
adapter = MetaWhatsAppAdapter()

@router.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    msg = adapter.parse_webhook(payload)
    if not msg: return {"status": "ignored"}
    result = await process_message(..., channel="whatsapp")
    if result.response:
        await adapter.send_message(config, msg.sender_id, result.response)
```

```python
# instagram.py после рефакторинга (~80 строк вместо 116)
adapter = MetaInstagramAdapter()

@router.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    msg = adapter.parse_webhook(payload)
    if not msg: return {"status": "ignored"}
    # + X-Hub-Signature-256 verification (см. Phase 4)
    result = await process_message(..., channel="instagram")
```

### 3.5 Dead code cleanup: `integrations/instagram.py`

`InstagramConnector` (92 строки) — не используется нигде. После рефакторинга:
- `send_message()` → уже в `MetaInstagramAdapter`
- `get_profile()`, `get_conversations()` → перенести в `MetaGraphClient` если нужны
- Удалить файл

**Оценка:** 6-8 часов. Новые файлы `base.py` + `meta_client.py` + рефакторинг двух роутеров + cleanup.

---

## 4. Фаза 2 — WhatsApp Embedded Signup (production)

**Зачем:** Клиент подключается без ручного ввода токенов. Тот же OAuth-паттерн, что уже работает для Instagram (но с важными фиксами — см. Phase 4).

### 4.1 Что нужно в `.env`

```
# Уже есть (для Instagram):
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
FACEBOOK_REDIRECT_URI=https://app.jeeves.dev/admin/api/integrations/whatsapp/callback

# Новое — необязательно, можно переиспользовать те же:
WHATSAPP_WABA_ID=                    # опционально, для регистрации вебхука
WHATSAPP_ACCESS_TOKEN=               # системный токен для регистрации подписок
```

### 4.2 `GET /api/integrations/whatsapp/auth`

```python
@router.get("/api/integrations/whatsapp/auth")
def whatsapp_auth(request: Request):
    """Redirect to Meta Embedded Signup dialog."""
    settings = get_settings()
    fb_url = (
        f"https://www.facebook.com/v22.0/dialog/oauth"
        f"?client_id={settings.facebook_app_id}"
        f"&redirect_uri={settings.facebook_redirect_uri or str(request.base_url) + 'admin/api/integrations/whatsapp/callback'}"
        f"&scope=whatsapp_business_messaging,business_management"
        f"&response_type=code"
    )
    return RedirectResponse(url=fb_url)
```

**Scopes:**
- `whatsapp_business_messaging` — отправка/получение сообщений
- `business_management` — доступ к WABA (нужен для регистрации webhook)
- `pages_show_list` — просмотр бизнес-аккаунтов

### 4.3 `GET /api/integrations/whatsapp/callback`

```python
@router.get("/api/integrations/whatsapp/callback")
async def whatsapp_callback(code: str = "", ...):
    """Exchange code → long-lived token → register webhook → save."""

    # 1. Code → Access Token
    r = httpx.post("https://graph.facebook.com/v22.0/oauth/access_token", data={
        "client_id": settings.facebook_app_id,
        "client_secret": settings.facebook_app_secret,
        "redirect_uri": settings.facebook_redirect_uri or ...,
        "code": code,
    })
    token_data = r.json()
    user_access_token = token_data["access_token"]

    # 2. Получить WABA, phone_number_id
    # GET /me/businesses → business_id
    # GET /{business_id}/client_waba → waba_id
    # GET /{waba_id}/phone_numbers → phone_number_id, display_phone

    # 3. Получить долгоживущий токен для номера
    # GET /{phone_number_id}?fields=... → проверяем верификацию

    # 4. Зарегистрировать webhook:
    # POST /{app_id}/subscriptions (системный токен)
    # POST /{phone_number_id}/subscribed_apps

    # 5. Сгенерировать verify_token
    verify_token = secrets.token_urlsafe(32)

    # 6. Сохранить в ChannelConfig
    config = {
        "phone_number_id": phone_number_id,
        "access_token": permanent_token,
        "verify_token": verify_token,
        "business_phone": display_phone,
        "provider": "meta",
        "waba_id": waba_id,
    }
    upsert_channel(db, tenant.id, "whatsapp", config, status="active")
    return {"ok": True, "connected": True, "phone": display_phone}
```

### 4.4 Авто-регистрация webhook

Для регистрации вебхука без участия клиента нужен **system access token** (принадлежит приложению, не пользователю):

```python
# Регистрация подписки на приложение
# Выполняется 1 раз при деплое, не при онбординге
POST /{app_id}/subscriptions
  ?access_token={system_token}
  &object=whatsapp_business_messaging
  &callback_url=https://app.jeeves.dev/channels/whatsapp/webhook
  &fields=messages
  &verify_token={generated}

# Подписка номера на уведомления
# Выполняется при онбординге каждого tenant'а
POST /{phone_number_id}/subscribed_apps
  ?access_token={user_access_token}
```

**Важно:** Системный access_token — в `config.py`, не в `.env` tenant'а. Нужен Meta App ID + App Secret с правами `whatsapp_business_management`.

### 4.5 generate verify_token

Генерируется на бэкенде при онбординге, сохраняется в `ChannelConfig.config.verify_token`. Никто не вводит его вручную.

**Оценка:** 6-8 часов. 90% кода — повторение Instagram OAuth паттерна. Новая логика только в получении WABA + phone_number_id и регистрации подписок.

---

## 5. Фаза 3 — Provider Routing & Admin UI

### 5.1 `channels/router.py` — единый роутер

```python
_ADAPTERS: dict[str, type[ChannelAdapter]] = {
    "meta": MetaWhatsAppAdapter,
    "twilio_dev": TwilioAdapter,
}

def get_adapter(provider: str) -> ChannelAdapter:
    cls = _ADAPTERS.get(provider)
    if not cls: raise ValueError(f"Unknown provider: {provider}")
    return cls()

async def send_message(
    db: Session, tenant_id: UUID, recipient_id: str, text: str
) -> SendResult:
    channel = get_channel_with_fallback(db, tenant_id)
    config = channel.config
    provider = config.get("provider", "meta")
    adapter = get_adapter(provider)
    return await adapter.send_message(config, recipient_id, text)
```

### 5.2 Admin UI — `integration_hub.html`

**Добавить на страницу Integrations:**

```html
<!-- WhatsApp card — переработать текущую -->
<div class="integration-card">
  <div class="card-header">
    <span class="card-icon">💬</span>
    <span class="card-title">WhatsApp</span>
    <span class="pill status" id="whatsapp-status">Not connected</span>
  </div>

  <!-- Если не подключено — кнопка Connect через OAuth -->
  <button onclick="location.href='/admin/api/integrations/whatsapp/auth'"
          class="btn accent" id="whatsapp-connect-btn">
    Connect WhatsApp
  </button>

  <!-- Если подключено — показать номер + Disconnect -->
  <div id="whatsapp-connected" style="display:none">
    <div class="connected-phone">
      <span class="status-dot ok"></span>
      <span id="whatsapp-phone"></span>
    </div>
    <div class="connected-meta">
      <span class="pill ok">Embedded Signup</span>
      <button class="ghost danger" onclick="disconnectWhatsApp()">Disconnect</button>
    </div>
  </div>
</div>

<!-- Twilio Dev card — отдельная маленькая карточка, только для dev -->
<div class="integration-card" id="twilio-card">
  <div class="card-header">
    <span>🧪 Twilio Sandbox</span>
  </div>
  <button onclick="showTwilioModal()" class="btn sm">Configure Twilio</button>
</div>
```

### 5.3 Provider fallback logic

```python
# Если tenant не указал provider — используем meta (production default)
# Если tenant использует "twilio_dev" — только для dev/тестов
_WHATSAPP_PROVIDER_PRIORITY = ["meta", "twilio_dev"]
```

**Оценка:** 4-5 часов. UI изменения в 1 файле.

---

## 6. Фаза 4 — Instagram-Specific Optimizations (& Shared Fixes)

**Зачем:** У Instagram есть критические баги и missing features, которые надо исправить до продакшна. Часть фиксов общая для всех Meta-каналов.

### 6.1 `X-Hub-Signature-256` верификация (оба канала)

Сейчас ни Instagram, ни WhatsApp не проверяют сигнатуру входящих webhook'ов. Любой, кто знает URL, может отправить фальшивое сообщение.

```python
# shared/meta_webhook.py
import hmac, hashlib

def verify_signature(payload: bytes, signature_header: str, app_secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        app_secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```

**Где применяется:**
- `channels/instagram.py` — POST /webhook
- `channels/whatsapp.py` — POST /webhook

**Хранить app_secret:** в `ChannelConfig.config.webhook_secret` (tenant-scoped). Генерируется при OAuth онбординге.

### 6.2 Instagram OAuth: generate `verify_token`

**Текущий баг:** Instagram OAuth callback (`integrations_hub.py:438`) сохраняет конфиг без `verify_token`. Когда Meta присылает GET /webhook с `hub.verify_token`, в конфиге нет совпадающего токена → верификация проваливается.

**Фикс:** Генерировать `secrets.token_urlsafe(32)` в OAuth callback и сохранять в config:

```python
config = {
    "access_token": page_token,
    "business_page_id": page_id,
    "instagram_account_id": ig_account_id,
    "verify_token": secrets.token_urlsafe(32),       # ← NEW
    "webhook_secret": secrets.token_urlsafe(32),      # ← NEW: для X-Hub-Signature
}
```

Тот же фикс применить к WhatsApp OAuth (Phase 2).

### 6.3 Instagram `_resolve_tenant` cache fallback fix

**Текущий баг:** В `channels/instagram.py:33` fallback сравнивает `cfg.config.get("instagram_account_id")` с `ig_user_id` (sender ID). Это сравнение tenant's account ID vs sender's user ID — бессмысленно. Fallback почти никогда не сработает.

**Фикс:** При отсутствии cache entry — логировать warning и возвращать `(None, None)`. Cache строится на startup:

```python
def _resolve_tenant(db, sender_id):
    entry = channel_cache.resolve_instagram(sender_id)
    if entry:
        return db.get(Tenant, entry[0]), db.get(ChannelConfig, entry[1])
    logger.warning("Instagram cache miss for sender %s", sender_id)
    return None, None
```

### 6.4 Instagram OAuth: page selection

**Текущий баг:** Берётся только `pages[0]`. Если у пользователя несколько Facebook Pages, нет выбора.

**Фикс:** В OAuth callback — если `len(pages) > 1`, возвращать список страниц и просить пользователя выбрать:

```python
# callback response при нескольких страницах
if len(pages) > 1:
    return {
        "needs_page_selection": True,
        "pages": [{"id": p["id"], "name": p["name"]} for p in pages],
    }
# Фронтенд показывает выбор и отправляет POST /api/integrations/instagram/select-page
```

**Этот же UX понадобится для WhatsApp** (выбор бизнес-аккаунта / номера).

### 6.5 Instagram message deduplication

Meta может ределиверить webhook'и. В `whatsapp.py` есть `deduplication_key`. В Instagram — нет.

**Фикс:** Использовать Meta message ID как dedup key (есть в `messaging[].message.mid`):

```python
msg_id = msg.get("message", {}).get("mid", "")
if msg_id and msg_id in _processed_ids:
    continue
_processed_ids.add(msg_id)
```

Или (лучше) — in-memory set с TTL (через `cachetools.TTLCache`).

### 6.6 Instagram consent_required_channels

**Текущий пропуск:** `consent_required_channels = "whatsapp,widget"` в `config.py:57` — Instagram не включён.

**Фикс:** Добавить `"instagram"` в список.

### 6.7 Token refresh (Meta каналы)

Facebook Page tokens живут ~60 дней. Нет механизма рефреша.

**Вариант решения:** Background job (через существующий scheduler в `core/workflows/`), который:
1. Раз в 7 дней проверяет все active Meta-каналы
2. Для каждого вызывает `GET /{user-id}?fields=access_token&access_token={current}`
3. Обновляет token в ChannelConfig

```python
# shared/token_refresh.py
async def refresh_meta_tokens(db: Session):
    channels = db.execute(
        select(ChannelConfig).where(
            ChannelConfig.channel_type.in_(["whatsapp", "instagram"]),
            ChannelConfig.status == "active",
        )
    ).scalars().all()
    for ch in channels:
        token = ch.config.get("access_token", "")
        if not token: continue
        # Facebook returns a new token with extended expiry
        r = await client.get(f"{BASE}/me", params={
            "fields": "access_token",
            "access_token": token,
        })
        new_token = r.json().get("access_token", "")
        if new_token and new_token != token:
            ch.config["access_token"] = new_token
            ch.config["token_refreshed_at"] = datetime.utcnow().isoformat()
    db.commit()
```

### 6.8 Media message handling (Instagram)

Instagram webhook может содержать фото, видео, истории, реакции. Сейчас обрабатывается только `message.text`.

**Минимальный фикс:** Для медиа-сообщений извлекать caption / подпись:

```python
text = message.get("text", "")
if not text:
    attachments = message.get("attachments", [])
    for att in attachments:
        if att.get("type") == "image" and att.get("payload", {}).get("url"):
            payload = att["payload"]
            text = payload.get("title", "") or f"[Image: {payload['url']}]"
```

**Оценка (Phase 4):** 10-12 часов. Большая часть — токен-рефреш джоба и page selection UI.

---

## 7. UX/UI Design & Scenarios

**Зачем:** Админка используется клиниками ежедневно. Подключение WhatsApp/Instagram — критический путь онбординга. Каждый сценарий (успех, ошибка, timeout, revoke) должен иметь понятный UX без dead-end состояний.

### 7.1 State machine для channel-карточки

Каждый канал проходит через следующие состояния. UI должен отображать текущее состояние + доступные действия:

```
                  ┌─────────────┐
                  │ not_configured │
                  └──────┬──────┘
                         │ Click "Connect"
                         ▼
                  ┌─────────────┐
                  │  connecting  │  ← Окно Meta OAuth открыто
                  └──────┬──────┘
                    ┌────┴────┐
                    ▼         ▼
            ┌──────────┐  ┌────────┐
            │  active   │  │ error  │  ← Ошибка OAuth / отказ прав
            └────┬─────┘  └───┬────┘
                 │            │
                 │ token      │ Click "Retry"
                 │ expires    │
                 ▼            │
            ┌──────────┐      │
            │ expired  │──────┘
            └────┬─────┘
                 │ Click "Reconnect"
                 ▼
              connecting (loop)
```

| State | Pill color | Card action | Detail shown |
|-------|-----------|-------------|-------------|
| `not_configured` | `.pill.muted` | "Connect" (accent btn) | — |
| `connecting` | `.pill.warn` с spinner | Disabled btn | "Connecting..." |
| `active` | `.pill.ok` | "Disconnect" (ghost danger) | Номер/account, provider, connected date |
| `error` | `.pill.err` | "Retry" (warn btn) | Текст ошибки |
| `expired` | `.pill.warn` | "Reconnect" (accent btn) | "Token expired — reconnect" |

### 7.2 OAuth flow UX

```
┌─ Admin Panel ─────────────────────────────────────┐
│                                                    │
│  Instagram Card / WhatsApp Card                    │
│  ┌─────────────────────────────────────────────┐   │
│  │  [Connect Instagram]  [Connect WhatsApp]    │   │
│  └─────────────────────────────────────────────┘   │
│           │                                        │
│           ▼                                        │
│  ┌─ Full page redirect ─────────────────────────┐  │
│  │  → https://www.facebook.com/v22.0/dialog/oauth│  │
│  │  User логинится в Meta, выбирает аккаунт,     │  │
│  │  принимает permissions + DPA                   │  │
│  │                                               │  │
│  │  3 возможных исхода:                          │  │
│  │  ✅ User accepts → callback → success         │  │
│  │  ❌ User declines → callback → error page     │  │
│  │  ⏳ User closes window → timeout → retry       │  │
│  └───────────────────────────────────────────────┘  │
│                                                    │
└────────────────────────────────────────────────────┘
```

**Окно Meta OAuth** — это redirect всего окна, не popup (попап-блокеры, мобильные проблемы).

**Что показать пользователю при redirect обратно в админку:**

```html
<!-- /admin/api/integrations/whatsapp/callback?code=xxx -->
<!-- Во время обработки на бэкенде: -->
<div class="loading-screen" id="oauth-processing">
  <div class="spinner"></div>
  <p>Connecting WhatsApp, please wait...</p>
  <p class="muted">This may take a few seconds</p>
</div>

<!-- После успеха (redirect на /admin/integrations): -->
<div class="hub-section">
  <div class="pill ok">✓ WhatsApp connected</div>
  <div class="connected-info">
    <span class="phone-display">+31 6 12345678</span>
    <span class="provider-tag">Meta Cloud API</span>
  </div>
</div>

<!-- После ошибки — показать на странице integrations: -->
<div class="alert err">
  <strong>Connection failed</strong>
  <p id="oauth-error-message">${error_detail}</p>
  <button onclick="retryOAuth('whatsapp')" class="btn">Try Again</button>
  <button onclick="showManualConfig('whatsapp')" class="ghost">Manual Setup</button>
</div>
```

**Обработка callback на фронтенде:**

Сейчас Instagram OAuth callback — это синхронный endpoint, который делает redirect обратно на `/admin/integrations` (в коде нет, но так работает). Нужно, чтобы callback:
1. При успехе — показывал flash message + обновлённую страницу
2. При ошибке — показывал сообщение об ошибке с кнопками Retry / Manual Setup

```python
# callback endpoint — возвращает HTML-страницу, не JSON
@router.get("/api/integrations/whatsapp/callback")
def whatsapp_callback(request, code, db, tenant):
    try:
        # ... OAuth exchange ...
        return RedirectResponse(
            url="/admin/integrations?status=success&channel=whatsapp&phone=...",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/integrations?status=error&channel=whatsapp&detail={quote(str(e))}",
            status_code=303,
        )
```

```javascript
// integrations_hub.html — обработка query params при загрузке
const params = new URLSearchParams(window.location.search);
const oauthStatus = params.get('status');
const oauthChannel = params.get('channel');
if (oauthStatus === 'success') {
  showToast(`${oauthChannel} connected successfully!`, 'ok');
  history.replaceState({}, '', '/admin/integrations');
  loadIntegrations();
} else if (oauthStatus === 'error') {
  const detail = params.get('detail') || 'Unknown error';
  showOAuthError(oauthChannel, detail);
  history.replaceState({}, '', '/admin/integrations');
}
```

### 7.3 Page / Account selection UI

Когда у пользователя несколько Facebook Pages (или несколько WABA / phone numbers):

**Сценарий:** User auth → Meta возвращает token → бэкенд проверяет, сколько страниц/аккаунтов → если >1 → возвращает страницу выбора.

```python
# instagram OAuth callback — если pages > 1
if len(pages) > 1:
    return {
        "needs_page_selection": True,
        "pages": [{"id": p["id"], "name": p["name"], "picture": p.get("picture", {}).get("data", {}).get("url")}],
    }
```

```html
<!-- Selection UI — показывается как шаг в modal -->
<div id="pageSelectionStep" class="modal-step" style="display:none">
  <h3>Select Facebook Page</h3>
  <p class="muted">Multiple pages found. Choose which one to connect:</p>
  <div class="page-list" id="pageList">
    <!-- rendered by JS: -->
    <div class="page-option" data-page-id="123">
      <img src="..." class="page-avatar" />
      <span class="page-name">Clinic Amsterdam</span>
      <span class="page-check">✓</span>
    </div>
  </div>
  <button onclick="confirmPageSelection('instagram')" class="btn accent" id="confirmPageBtn">Confirm</button>
</div>
```

**Тот же UX для WhatsApp:**
1. После code → token: GET /me/businesses → GET /{business_id}/client_waba → если >1 WABA → выбор
2. После выбора WABA: GET /{waba_id}/phone_numbers → если >1 номер → выбор

### 7.4 Модал подключения: универсальный шаблон

Текущий UX: отдельные модалы для Instagram и WhatsApp с переключением OAuth/Manual. Предлагается **единый многошаговый модал**:

```
Step 1: Choose provider  [Meta Cloud API] [Twilio Sandbox] [Manual]
        │
        ▼
Step 2: Authorization
  ┌─ Meta ─────────────┐  ┌─ Twilio ──────────────┐  ┌─ Manual ──────────┐
  │ [Connect via Meta] │  │ Account SID           │  │ Phone Number ID   │
  │  (OAuth redirect)  │  │ Auth Token            │  │ Access Token      │
  │                     │  │ Sandbox Phone #      │  │ Verify Token      │
  │                     │  │ [Connect Twilio]     │  │ Business Phone    │
  └─────────────────────┘  └───────────────────────┘  │ [Connect Manual]  │
                                                       └───────────────────┘
        │
        ▼
Step 3: Confirmation
  ┌─────────────────────────────────────────────┐
  │  ✓ Connected!                               │
  │  Provider: Meta Cloud API                   │
  │  Phone: +31 6 12345678                      │
  │  WABA: 1234567890                           │
  │  Status: Active                             │
  │                                             │
  │  [Done]                                     │
  └─────────────────────────────────────────────┘
```

```html
<!-- Unified connector modal -->
<div class="modal-step" id="connStep1">
  <h3>Connect WhatsApp</h3>
  <div class="provider-options">
    <div class="provider-card" onclick="selectProvider('meta')">
      <img src="/static/logos/whatsapp.svg" />
      <strong>WhatsApp Cloud API</strong>
      <span class="muted">Production — Meta hosted</span>
    </div>
    <div class="provider-card" onclick="selectProvider('twilio')">
      <span class="pill warn">Dev Only</span>
      <strong>Twilio Sandbox</strong>
      <span class="muted">Testing & Development</span>
    </div>
    <div class="provider-card" onclick="selectProvider('manual')">
      <strong>Manual Setup</strong>
      <span class="muted">Enter credentials directly</span>
    </div>
  </div>
</div>
```

### 7.5 Disconnect flow с подтверждением

**Текущий баг:** disconnect сразу показывает spinner, нет возможности отменить.

**Новый flow:**

```html
<!-- Confirm modal — ДО начала disconnect -->
<div id="confirmModal" class="modal-overlay">
  <div class="modal confirm-modal">
    <div class="confirm-icon warn">⚠️</div>
    <div class="confirm-title">Disconnect WhatsApp?</div>
    <div class="confirm-desc">
      Your WhatsApp integration will be deactivated.
      Patients won't be able to reach you via WhatsApp until you reconnect.
    </div>
    <div class="confirm-actions">
      <button class="btn ghost" onclick="closeConfirm()">Cancel</button>
      <button class="btn danger" onclick="confirmDisconnect('whatsapp')">
        Disconnect
      </button>
    </div>
  </div>
</div>
```

**Дополнительно:** если канал active и есть активные диалоги за последние N дней — показать warning:

```html
<div class="confirm-desc">
  <strong>⚠ Active conversations detected</strong><br/>
  You have 12 active WhatsApp conversations. Disconnecting will
  prevent you from responding to these patients via Jeeves.
  <a href="/admin/inbox?channel=whatsapp">View conversations</a>
</div>
```

### 7.6 Toast notifications

Сейчас в integrations_hub нет toast (только modal-result). Добавить систему уведомлений для событий, не требующих модала:

| Event | Toast type | Duration |
|-------|-----------|----------|
| Token refreshed automatically | `.toast.info` | 4s |
| Connection lost (Meta API down) | `.toast.err` | Persistent |
| WhatsApp connected via OAuth | `.toast.ok` | 6s |
| QR code scanned | `.toast.ok` | 4s |

```html
<!-- Toast container — fixed position, bottom-right -->
<div id="toastContainer" class="toast-container"></div>

<style>
.toast-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.toast {
  padding: 12px 20px;
  border-radius: var(--radius);
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: 0 4px 24px rgba(0,0,0,0.4);
  animation: slideIn .3s ease, fadeOut .3s ease 3.7s forwards;
  max-width: 400px;
}
.toast.ok { border-left: 3px solid var(--green); }
.toast.err { border-left: 3px solid var(--red); }
.toast.info { border-left: 3px solid var(--accent); }
</style>

<script>
function showToast(msg, type = 'info', duration = 4000) {
  const container = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), duration);
}
</script>
```

### 7.7 Connection detail panel

Вместо простого pill "Connected" — показывать детали подключения прямо в карточке:

```html
<!-- WhatsApp card — connected state -->
<div class="hub-card" data-channel="whatsapp">
  <div class="hub-card-header">
    <img src="/static/logos/whatsapp.svg" class="hub-card-icon" />
    <div class="hub-card-body">
      <div class="hub-card-name">WhatsApp</div>
      <div class="hub-card-meta">
        <span class="pill ok">Connected</span>
        <span class="pill cyan provider-badge">Meta Cloud API</span>
      </div>
    </div>
    <button class="ghost danger sm" onclick="disconnectChannel('whatsapp')">
      Disconnect
    </button>
  </div>

  <!-- Expandable detail panel -->
  <div class="connection-detail" id="waDetail">
    <div class="detail-row">
      <span class="detail-label">Business Phone</span>
      <span class="detail-value">+31 6 12345678</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">WABA ID</span>
      <span class="detail-value mono">123456789012345</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Connected</span>
      <span class="detail-value">2 Mar 2026</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Token expires</span>
      <span class="detail-value warn">in 32 days</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Messages (30d)</span>
      <span class="detail-value">247 sent / 189 received</span>
    </div>
  </div>
  <button class="ghost sm" onclick="toggleDetail('waDetail')">
    Show details ▾
  </button>
</div>
```

### 7.8 Error states & recovery

| Scenario | UX | Recovery |
|----------|-----|----------|
| OAuth declined by user | Redirect back → show "Connection cancelled. You can try again or use manual setup." | Retry / Manual |
| OAuth callback timeout (Meta slow) | Loading screen >10s → timeout error | Retry |
| Token expired (background refresh failed) | Card shows `.pill.warn` "Token expired" | Reconnect via OAuth |
| API returns 401 on send | Log + auto-trigger token refresh; если refresh failed → set state `expired` | Background + notification |
| Meta API temporarily down (5xx) | Card shows `.pill.err` "Service unavailable" | Auto-retry with backoff |
| Webhook verification fails | Email alert to admin + card shows `.pill.err` "Webhook not receiving" | Regenerate verify_token |
| User revokes Facebook app | Next API call fails → state→`expired` | Reconnect |
| Twilio Sandbox rate limit | Silently retry with backoff; if persistent → card `.pill.warn` "Rate limited" | Upgrade to Meta |

### 7.9 Provider badge system

Каждый канал показывает, через какого провайдера он подключен:

```html
<!-- Provider badges — цветная метка в карточке -->
<span class="pill cyan provider-badge">
  <span class="provider-dot meta"></span> Meta Cloud API
</span>
<span class="pill warn provider-badge">
  <span class="provider-dot twilio"></span> Twilio Sandbox
</span>
```

```css
.provider-dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}
.provider-dot.meta { background: #1877F2; }  /* Facebook blue */
.provider-dot.twilio { background: #F22F46; } /* Twilio red */
.provider-badge { font-size: 11px; }
```

### 7.10 Loading screen при OAuth redirect

Пока Meta обрабатывает OAuth и редиректит обратно в админку, может пройти 2-5 секунд. Показать loading screen:

```html
<!-- Показывается при redirect на /admin/api/integrations/*/auth -->
<div id="oauthLoading" class="loading-overlay" style="display:none">
  <div class="loading-card">
    <div class="spinner-lg"></div>
    <h3>Redirecting to Facebook...</h3>
    <p class="muted">You'll be asked to authorize Jeeves to access your WhatsApp.</p>
    <p class="muted" id="oauthFallback">
      Not redirected?
      <a href="#" id="oauthDirectLink">Click here</a>
    </p>
  </div>
</div>

<script>
function startOAuth(url) {
  // показать loading screen
  document.getElementById('oauthLoading').style.display = 'flex';
  document.getElementById('oauthDirectLink').href = url;
  // fallback — если пользователь не ушёл через 2s, показать прямую ссылку
  setTimeout(() => {
    document.getElementById('oauthFallback').style.display = 'block';
  }, 2000);
  // redirect
  window.location.href = url;
}
</script>
```

### 7.11 Responsive considerations

Админка предполагается desktop-first, но мобильные планшеты используются:

| Breakpoint | Behaviour |
|-----------|-----------|
| >1024px | 3-column grid for channel cards |
| 768-1024px | 2-column grid |
| <768px | 1-column stack; modals full-screen |
| Modals на мобильных | `width: 100%; max-height: 100dvh; border-radius: 0;` |

### 7.12 UX/UI checklist для каждой фазы

| Phase | UX/UI work |
|-------|-----------|
| **P0 (Twilio)** | Twilio configure modal + card |
| **P1 (Abstract)** | Нет UI-изменений (рефакторинг бэкенда) |
| **P2 (WhatsApp OAuth)** | Loading screen, callback error handling, toast on success, page selection UX |
| **P3 (Admin UI)** | Новый unified modal, connection detail panel, provider badges, disconnect confirmation, responsive |
| **P4 (Instagram fixes)** | Instagram OAuth error handling, verify_token UI feedback, token expiry warning in card, disconnect confirmation |

**Оценка (UX/UI):** 6-8 часов дизайна + 4-6 часов фронтенд-реализации. Распределяется по фазам.

---

## 8. Testing Strategy

### 8.1 Component tests (mocked, no external API)

| Компонент | Инструмент |
|-----------|-----------|
| **TwilioAdapter.send_message** | `pytest` + `httpx` mock |
| **TwilioAdapter.parse_webhook** | `pytest` + fixtures |
| **MetaWhatsAppAdapter.send_message** | `pytest` + `httpx` mock |
| **MetaWhatsAppAdapter.parse_webhook** | `pytest` + Meta payload fixtures |
| **MetaInstagramAdapter.parse_webhook** | `pytest` + Meta payload fixtures |
| **OAuth callback (code → token)** | `pytest` + mock `httpx.post` (WhatsApp + Instagram) |
| **Instagram OAuth verify_token fix** | `pytest` — assert verify_token + webhook_secret in output config |
| **Webhook signature verification** | `pytest` — hmac test vectors |
| **Provider routing (get_adapter)** | `pytest` |
| **MetaGraphClient** | `pytest` + `respx` (mock router) |
| **Token refresh job** | `pytest` + mock `httpx.get` |
| **Instagram dedup** | `pytest` — verify duplicate mid ignored via TTLCache |
| **Page selection UX** | `pytest` — assert multiple pages returned with `needs_page_selection` |
| **End-to-end: Twilio → process_message** | Twilio Sandbox + тестовый WhatsApp |
| **End-to-end: Meta → process_message** | Embedded Signup с реальным Meta аккаунтом |

### 8.2 Test fixtures

```python
# tests/fixtures/channels.py
META_WHATSAPP_INBOUND = {
    "entry": [{
        "changes": [{
            "value": {
                "messages": [{
                    "from": "1234567890",
                    "text": {"body": "Hello"},
                    "timestamp": "1717000000",
                }],
                "metadata": {"phone_number_id": "123456"},
            }
        }]
    }]
}

META_INSTAGRAM_INBOUND_CONVERSATIONS = {
    "entry": [{
        "changes": [{
            "value": {
                "messages": [{
                    "from": "ig_user_123",
                    "text": "Hello from IG",
                    "id": "msg_abc123",
                }],
            }
        }]
    }]
}

# Legacy Send/Receive API format — keep for backward compat
META_INSTAGRAM_INBOUND_LEGACY = {
    "entry": [{
        "messaging": [{
            "sender": {"id": "ig_user_123"},
            "message": {
                "mid": "msg_abc123",
                "text": "Hello from IG",
                "is_echo": False,
            },
        }]
    }]
}

TWILIO_INBOUND_FORM = {
    "From": "whatsapp:+1234567890",
    "To": "whatsapp:+14155238886",
    "Body": "Hello from Twilio",
    "MessageSid": "SM123",
}

MOCK_META_TOKEN_RESPONSE = {
    "access_token": "EAATest123",
    "token_type": "bearer",
}

MOCK_MULTIPLE_PAGES = {
    "data": [
        {"id": "123", "name": "Clinic Amsterdam"},
        {"id": "456", "name": "Clinic Rotterdam"},
    ]
}

MOCK_WHATSAPP_WABA = {
    "data": [
        {"id": "waba_111", "name": "Production WABA"},
        {"id": "waba_222", "name": "Test WABA"},
    ]
}
```

### 8.3 CI pipeline

```yaml
- name: WhatsApp + Instagram channel tests
  run: pytest api/tests/ -v --tb=short -k "channel or twilio or instagram or whatsapp"
```

### 8.4 Coverage target

Все новые модули: >90%. Особое внимание:
- `base.py` — все adapter методы
- `meta_client.py` — все Graph API вызовы
- `twilio.py` — webhook parsing + send
- `shared/meta_webhook.py` — signature verification
- `integrations_hub.py` — OAuth endpoints (WhatsApp + Instagram fixes)

---

## 9. GDPR / Compliance

Аesthetic medicine = sensitive health data. Обязательно:

### 9.1 Data Processing Agreement

- Meta требует DPA для WhatsApp Business API. Клиент должен принять Meta DPA при онбординге.
- **В OAuth flow:** Meta сама показывает диалог с DPA. Клиент принимает до того, как мы получаем токен.
- **Для нас:** ничего не нужно — Meta берёт на себя compliance.

### 9.2 Минимизация данных

```python
# В process_message() — НЕ передаём исходный текст в Meta
# Только message_id, направление, метаданные
# PHI/PII остаётся в нашей БД (tenant-scoped)
```

### 9.3 Retention

```python
# Авто-удаление сообщений старше N дней
# config.yaml:
whatsapp:
  message_retention_days: 90  # default, настраивается
```

### 9.4 Opt-in / Opt-out

Уже реализовано в `whatsapp.py` (lines 143-161):
- `YES`, `OPT-IN`, `START`, `CONSENT` → `ConsentManager.record_consent()`
- `STOP`, `UNSUBSCRIBE`, `CANCEL`, `OPT-OUT` → `ConsentManager.revoke_consent()`

Ничего не ломаем.

### 9.5 Tenant-scoped изоляция

`ChannelConfig` — tenant-scoped. Один tenant не видит данные другого. Текущая модель `ChannelConfig(Base, _TenantScoped, ...)` уже это гарантирует.

### 9.6 Instagram consent fix

```python
# config.py — добавить "instagram" в consent_required_channels
consent_required_channels = "whatsapp,widget,instagram"
```

---

## 10. Files & Dependencies

### Новые файлы

| File | Purpose | Lines | Phase |
|------|---------|-------|-------|
| `api/app/channels/base.py` | `ChannelAdapter` ABC, dataclasses | ~60 | P1 |
| `api/app/channels/meta_client.py` | Shared MetaGraphClient (v22.0) | ~80 | P1 |
| `api/app/channels/twilio.py` | Twilio WhatsApp Sandbox adapter | ~150 | P0 |
| `api/app/channels/router.py` | Provider routing, `send_message()` entry | ~50 | P1 |
| `api/app/channels/adapters/whatsapp.py` | `MetaWhatsAppAdapter` | ~60 | P1 |
| `api/app/channels/adapters/instagram.py` | `MetaInstagramAdapter` | ~60 | P1 |
| `api/app/shared/meta_webhook.py` | `verify_signature()` utility | ~20 | P4 |
| `api/app/shared/token_refresh.py` | Background token refresh job | ~60 | P4 |
| `api/tests/test_channel_twilio.py` | Twilio adapter tests | ~120 | P0 |
| `api/tests/test_channel_meta.py` | Meta adapter tests (WhatsApp + Instagram) | ~150 | P1 |
| `api/tests/test_channel_oauth.py` | OAuth callback tests (both) | ~100 | P2 |
| `api/tests/test_meta_webhook.py` | Signature verification tests | ~50 | P4 |
| `api/tests/test_token_refresh.py` | Token refresh job tests | ~60 | P4 |

### Изменяемые файлы

| File | Changes |
|------|---------|
| `api/app/channels/whatsapp.py` | Рефакторинг: вынести send/parse в `MetaWhatsAppAdapter`, роутер ~80 строк |
| `api/app/channels/instagram.py` | Рефакторинг: вынести send/parse в `MetaInstagramAdapter`, fix dedup, add signature verification |
| `api/app/admin/integrations_hub.py` | Добавить OAuth endpoints: `/whatsapp/auth`, `/whatsapp/callback`, `/twilio/configure`; fix Instagram OAuth (verify_token, webhook_secret, page selection) |
| `api/app/admin/integrations_hub.html` | Обновить WhatsApp card + Instagram card (page selection UX) |
| `api/app/config.py` | Добавить `"instagram"` в `consent_required_channels`; возможно `facebook_redirect_uri` для WhatsApp |
| `api/main.py` | Добавить `app.include_router(twilio_channel.router)` |
| `api/app/channels/registry.py` | Добавить `twilio_dev` в `SUPPORTED_CHANNELS` |
| `api/app/channels/__init__.py` | Экспорт новых модулей |

### Зависимости

| Пакет | Зачем | Уже есть? |
|-------|-------|-----------|
| `httpx` | HTTP-клиент для Meta, Twilio API | Да |
| `fastapi` | Роутеры, Depends | Да |
| `respx` | Mock HTTP-роутер для тестов Graph API | Нет, test dep |
| `cryptography` | Webhook signature verification (Twilio) | Нет, optional |

**twilio SDK не нужен** — используем прямой REST API через httpx. **respx** — только для тестов.

---

## 11. Rollback

### Пофазовый rollback

| Фаза | Rollback |
|------|----------|
| Phase 0 (Twilio) | Удалить `twilio.py`, убрать `include_router` из `main.py` |
| Phase 1 (Abstract + MetaClient) | Удалить `base.py`, `meta_client.py`, `router.py`, `adapters/`; `whatsapp.py` + `instagram.py` из git restore |
| Phase 2 (OAuth) | Удалить endpoints из `integrations_hub.py`, template changes из git |
| Phase 3 (UI) | `git checkout` для `integrations_hub.html` |
| Phase 4 (Instagram + Shared) | Удалить `shared/meta_webhook.py`, `shared/token_refresh.py`; откатить `integrations_hub.py` фиксы |

### Feature flags

```python
# config.yaml
whatsapp:
  enabled: true
  embedded_signup: true    # если false — показываем ручной ввод
  twilio_dev: false         # true только для dev окружения
instagram:
  enabled: true
```

### А что если Meta заблокирует приложение?

OAuth endpoints не работают → клиент не может подключиться. В этом случае:
- Показываем в UI альтернативный ручной ввод (текущий flow)
- Tenants с уже подключёнными аккаунтами продолжают работать
- Twilio Sandbox как fallback для dev

---

## 12. Instagram Optimization — Audit Findings

**Источник:** Полный аудит кода Instagram-канала от 09.06.2026.

### 12.1 Текущее состояние

Компонент | Файл | Строк | Статус
---------|------|-------|-------
Webhook handler | `channels/instagram.py` | 116 | Работает, но с багами
Admin OAuth | `integrations_hub.py:331-448` | 117 | Есть, но с багами
Connector (dead) | `integrations/instagram.py` | 92 | Никем не используется
Admin UI | `templates/integrations_hub.html` | ~80 (IG part) | Работает
Tests | `tests/test_whatsapp_messaging.py:296` | 1 line | Практически нет

### 12.2 Critical bugs (HIGH — блокируют продакшн)

| # | Баг | Файл:строка | Фикс в Phase |
|---|-----|------------|-------------|
| 1 | **Нет `verify_token` в OAuth callback** → webhook verification fails | `integrations_hub.py:438` | P4 (6.2) |
| 2 | **`_resolve_tenant` cache fallback сравнивает account_id с user_id** (бессмысленно) | `channels/instagram.py:33` | P4 (6.3) |
| 3 | **Нет `X-Hub-Signature-256` верификации** — любой может слать фальшивые webhook'и | `channels/instagram.py:76` | P4 (6.1) |
| 4 | **Только первый Facebook Page** — нет выбора при нескольких страницах | `integrations_hub.py:425` | P4 (6.4) |

### 12.3 Important improvements (MEDIUM)

| # | Улучшение | Текущий баг | Phase |
|---|-----------|------------|-------|
| 5 | **Нет token refresh** — токен expires через ~60 дней | Token expires, клиент должен переподключаться | P4 (6.7) |
| 6 | **`InstagramConnector` — dead code** | `integrations/instagram.py` не используется | P1 (3.5) |
| 7 | **API version inconsistency** | WhatsApp v17.0, Instagram v22.0 | P1 (3.2) — MetaGraphClient |
| 8 | **Нет deduplication** | Meta может ределиверить webhook'и | P4 (6.5) |
| 9 | **Instagram не в consent_required_channels** | Compliance gap | P4 (6.6) |
| 10 | **Только text messages** | Игнорирует фото/видео caption | P4 (6.8) |
| 11 | **`int(challenge)` fragile** | Если challenge non-numeric → crash | P4 (6.1) |
| 12 | **Дублирование `_IG_GRAPH_API`** | В 2 местах, могут рассинхрониться | P1 (3.2) |

### 12.4 Zero tests

| Компонент | Tests |
|-----------|-------|
| `channels/instagram.py` webhook handler | 0 |
| `channels/instagram.py` send_message | 0 |
| `integrations_hub.py` Instagram OAuth | 0 |
| `integrations/instagram.py` InstagramConnector | 0 |

Все будут добавлены в соответствующих фазах (см. раздел Testing).

### 12.5 Оптимальный порядок имплементации

```
Phase 1 (Abstract + MetaGraphClient) ────────────────────┐
  включает refactor instagram.py → MetaInstagramAdapter   │
  cleanup integrations/instagram.py (dead code)            │
      │                                                   │
      ▼                                                   │
Phase 4 (Instagram fixes) ────────────────────────────────┤
  verify_token in OAuth                                    │
  cache fallback fix                                       │
  webhook signature verification                           │
  dedup                                                    │
  consent_required_channels                                │
  media messages                                           │
      │                                                   │
      ▼                                                   │
Phase 2/3 (WhatsApp OAuth + Admin UI) ────────────────────┤
  Instagram OAuth fixes applied as template for WhatsApp   │
  Page selection UX shared между каналами                   │
      │                                                   │
      ▼                                                   │
Phase 4b (Token refresh background job) ──────────────────┘
  shared между Instagram + WhatsApp
```

---

## 13. Dependency Graph (Optimized)

```
Phase 0 (Twilio Sandbox) ──────────────────────────────────────┐
      │                                                         │
      ▼                                                         │
Phase 1 (Abstract Channel + MetaGraphClient) ←── dep on P0 ────┤
  ├─ refactor whatsapp.py → MetaWhatsAppAdapter                │
  ├─ refactor instagram.py → MetaInstagramAdapter              │
  ├─ backup integrations/instagram.py (dead code)              │
  └─ upgrade WhatsApp API v17.0 → v22.0                        │
      │                                                         │
      ▼                                                         │
Phase 2 (Webhook Security + Bugfixes) ←── dep on P1 ───────────┤
  ├─ X-Hub-Signature-256 (both channels)                       │
  ├─ Instagram: resolve_tenant cache fix                       │
  ├─ Instagram: dedup via TTLCache                              │
  ├─ Instagram: verify_token + webhook_secret in OAuth         │
  ├─ Instagram: media message handling                         │
  ├─ Instagram: consent_required_channels fix                  │
  └─ tests for ALL fixes                                        │
      │                                                         │
      ▼                                                         │
Phase 3 (Instagram OAuth Optimization) ←── dep on P2 ──────────┤
  ├─ Page selection UI and endpoint                             │
  ├─ OAuth flow UX: loading screen, toasts, errors             │
  ├─ InstagramDisconnect confirmation                           │
  └─ Tests: Instagram OAuth flow                                │
      │                                                         │
      ▼                                                         │
Phase 4 (WhatsApp Embedded Signup) ←── dep on P3 ──────────────┤
  ├─ WhatsApp-specific OAuth (different scopes + endpoints)    │
  ├─ WABA / phone number selection                             │
  ├─ Phone number verification UX                              │
  ├─ Webhook auto-registration                                 │
  ├─ WhatsApp opt-in recording (business-side consent)         │
  └─ Tests: WhatsApp OAuth                                     │
      │                                                         │
      ▼                                                         │
Phase 5 (Admin UI + Routing) ←── dep on P3, P4 ───────────────┤
  ├─ Unified provider selection modal                          │
  ├─ Connection detail panels (expandable)                     │
  ├─ Provider badges (Meta / Twilio)                           │
  ├─ Disconnect confirmation (with active conversation count)  │
  ├─ Toast notifications                                       │
  └─ Responsive grid (3/2/1 columns)                           │
      │                                                         │
      ▼                                                         │
Phase 6 (Production Readiness) ←── dep on P4, P5 ─────────────┤
  ├─ Meta App Review: submit for required permissions          │
  │   (whatsapp_business_messaging, instagram_manage_messages) │
  ├─ WhatsApp template message setup for clinics               │
  │   (appointment reminders, marketing opt-in)                 │
  ├─ Rate limit handling (backoff + alert)                     │
  ├─ Token refresh background job (shared both channels)       │
  ├─ DPA between Jeeves and clinics (GDPR)                    │
  └─ WhatsApp opt-in audit trail (store proof of consent)     │
```

## 14. Time Estimate (Optimized)

| Phase | Часы | Зависимости | Ключевые риски |
|-------|-------|-----------|---------------|
| P0 — Twilio Sandbox | 4-6 | Нет | Низкий |
| P1 — Abstract + MetaGraphClient | 6-8 | P0 | Средний: рефакторинг ломает существующие webhook'и |
| P2 — Webhook Security + Bugfixes | 8-10 | P1 | Низкий (изолированные изменения) |
| P3 — Instagram OAuth Optimization | 6-8 | P2 | Средний: OAuth callback changes |
| P4 — WhatsApp Embedded Signup | 10-14 | P3 | **Высокий**: Meta App Review, phone number requirements |
| P5 — Admin UI + Routing | 6-8 | P3, P4 | Низкий |
| P6 — Production Readiness | 10-14 | P4, P5 | **Высокий**: Meta App Review timeline (1-4 weeks) |
| **Subtotal** | **50-68** | | |
| Tests (внутри каждой фазы) | 7-10 | — | |
| **Total** | **57-78** | | |

### Параллельные треки

```
Week 1:   P0 ──▶ P1 ──▶ P2 ──▶
Week 2:   P2 ──▶ P3 ──▶
Week 3:   P3 ──▶ P4 ────────▶ P5 (UI параллельно с P4)
Week 4:   P4 ──▶ P5 ──▶
Week 5-6: P6 (Meta App Review — может занять 1-4 недели)
          └── параллельно: Token refresh, Rate limiting, DPA
```

---

## 15. Critical Review & Optimization

### 15.1 Critical issues found (HIGH — блокируют production)

| # | Проблема | Где в плане | Риск | Фикс |
|---|----------|------------|------|------|
| 1 | **WhatsApp "Embedded Signup" ≠ обычный OAuth.** План описывает стандартный OAuth, но WhatsApp требует WhatsApp Business Platform — другой набор API, scopes, token types. `whatsapp_business_messaging` scope + System User token, не Page token. | Phase 2 | Meta отклонит токен — integration не работает | Переписать Phase 4: WhatsApp OAuth использует WhatsApp Business Management API, не Instagram-паттерн |
| 2 | **Meta App Review не упомянут.** Все WhatsApp и Instagram API требуют App Review для production. `instagram_manage_messages`, `whatsapp_business_messaging` —都需要 approval. Это 1-4 недели. | Нет в плане | Кликнем "Go Live" — Meta блокирует | Добавить Phase 6: Production Readiness — App Review, submission checklist |
| 3 | **WhatsApp phone number requirements.** Номер НЕ может быть зарегистрирован в WhatsApp Messenger. Должен принимать SMS/call. Многие номера клиник уже имеют WhatsApp. | Phase 2 | Клиент вводит номер → ошибка | Добавить phone verification step в Phase 4 UI |
| 4 | **WhatsApp template messages не учтены.** Клинки need appointment reminders, marketing. WhatsApp blocks business-initiated messages without pre-approved templates. | Нет в плане | Клинки не могут отправлять напоминания | Добавить template setup + approval workflow в Phase 6 |
| 5 | **Instagram использует устаревший Send/Receive API.** `entry[].messaging[]` формат. Meta мигрирует на Conversations API (`entry[].changes[].value[]` как WhatsApp). | Phase 1/4 | В будущем Meta отключит Send/Receive | `MetaInstagramAdapter` должен поддерживать оба формата, с приоритетом Conversations API |
| 6 | **Phase ordering неправильный.** Instagram OAuth фиксы (verify_token, page selection) должны быть ДО WhatsApp OAuth, чтобы lessons learned применились. | Dependency Graph | Двойная работа: те же баги повторим в WhatsApp | Restructured phases (см. 13. Dependency Graph) |
| 7 | **Token refresh endpoint неправильный.** План использует `GET /me?fields=access_token`, но для Page tokens нужно `GET /{page_id}?fields=access_token`, для WhatsApp — System User refresh. | Phase 4 | Token refresh не работает | Fix endpoint per channel type в Phase 6 |

### 15.2 Medium issues found

| # | Проблема | Риск | Фикс |
|---|----------|------|------|
| 8 | **Rate limits не упомянуты.** WhatsApp: 250 msg/день marketing, 1M/24h utility. Instagram: ~200 msg/день. | При массовой рассылке — блокировка | Добавить rate limit handling + backoff в Phase 6 |
| 9 | **GDPR: DPA между Jeeves и клиниками.** План упоминает только Meta DPA. Но clinic — data controller, Jeeves — processor. Нужен DPA для health data. | GDPR violation | Добавить DPA requirement в Phase 6 |
| 10 | **WhatsApp opt-in audit trail.** WhatsApp требует proof of opt-in. Сейчас `process_message()` handles opt-in keywords, но нет записи бизнес-стороны (форма на сайте, согласие в клинике). | При аудите Meta — блокировка | Add opt-in recording + storage в Phase 6 |
| 11 | **Instagram dedup: `_processed_ids` растёт бесконечно.** In-memory set без TTL — память течёт. | OOM при долгой работе | Использовать `cachetools.TTLCache(maxsize=10000, ttl=300)` |
| 12 | **Twilio Sandbox ≠ production WhatsApp.** Twilio тоже требует Meta-approved WABA для production. Sandbox — только для dev. | Клик думает Twilio = production | Чётко маркировать "Dev Only" в UI |
| 13 | **OAuth callback: page selection требует другого UX.** При >1 страницы callback не может вернуть JSON (redirect flow). Нужен POST endpoint для выбора. | Page selection не работает | В Phase 3: callback → первый раз показывает HTML selection page |
| 14 | **Testing Strategy: нет тестов для page selection.** | Регрессия | Добавить тесты в 8.1 |
| 15 | **WhatsApp API version inconsistency.** План использует v22.0 для Instagram, но WhatsApp current code на v17.0. | Разные версии → разное поведение | Phase 1: upgrade WhatsApp к v22.0 |
| 16 | **"Минимальный запускаемый продукт" неверный.** План говорит Phase 0 + Phase 3. Но Phase 3 зависит от Phase 2 (OAuth) и Phase 4 (Instagram fixes). | Нереалистичные ожидания | Исправить: MVP = P0 + P1 + P2 (Twilio + security + fixes) |

### 15.3 Restructured phases (summary)

| Новый | Старый | Изменения |
|-------|--------|-----------|
| **P0** — Twilio Sandbox | P0 | Без изменений |
| **P1** — Abstract + MetaGraphClient + refactor | P1 | + upgrade WhatsApp API v17.0→v22.0 |
| **P2** — Webhook Security + Bugfixes | P4 (частично) | **Перенесён раньше**. Signature, cache fix, dedup, verify_token, consent, media |
| **P3** — Instagram OAuth Optimization | P4 (частично) | Page selection, error UX, tests |
| **P4** — WhatsApp Embedded Signup | P2 | **Переписан**: WhatsApp-specific API, phone verification, webhook registration, opt-in |
| **P5** — Admin UI + Routing | P3 | Дождается P3+P4 |
| **P6** — Production Readiness | **Новый** | App Review, templates, rate limits, token refresh, DPA, opt-in audit |

### 15.4 Что остаётся без изменений

- **Архитектура** (раздел 1) — provider-agnostic routing, двухслойный подход
- **Phase 0** (Twilio) — без изменений
- **UX/UI раздел** (7) — полностью актуален
- **GDPR** (9) — дополнен DPA requirement
- **Files & Dependencies** (10) — актуально
- **Rollback** (11) — актуально (добавить P5, P6)
- **Audit Findings** (12) — актуально (баги распределены по P2, P3)
