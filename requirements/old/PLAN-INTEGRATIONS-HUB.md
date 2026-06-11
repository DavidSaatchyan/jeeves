# Phase: Integration Hub (from `new-structure.md` ////555////)

## Цель

Объединить разрозненные страницы подключений (Cliniko, Pabau, Channels) в единый **Integration Hub** — экран-агрегатор всех внешних сервисов клиники со статусами, пошаговыми модалками подключения и кросс-ссылками на агентов.

## Текущее состояние

| Компонент | Существует? | Где |
|-----------|-------------|-----|
| Cliniko connector | ✅ Да | `integrations/cliniko.py` |
| Pabau connector | ✅ Да | `integrations/pabau.py` |
| CRM resolver (фабрика) | ✅ Да | `integrations/resolver.py` |
| CRM webhooks | ✅ Да | `integrations/webhooks.py` |
| Cliniko UI (страница + API) | ✅ Да | `admin/cliniko.py` + `cliniko_connections.html` |
| Pabau UI (страница + API) | ✅ Да | `admin/pabau.py` + `pabau_connections.html` |
| WhatsApp channel | ✅ Да | `channels/whatsapp.py` |
| Widget channel | ✅ Да | `channels/widget.py` |
| Channels registry (CRUD + cache) | ✅ Да | `channels/registry.py` |
| Channels UI | ✅ Да | `admin/pages.py` (`/api/channels`) + `channels.html` |
| WhatsApp QR-код аутентификация | ❌ Нет | Только ручной ввод токенов |
| Instagram connector | ❌ Нет | Вообще нет |
| Instagram канал в SUPPORTED_CHANNELS | ❌ Нет | Только `web_widget`, `whatsapp` |
| Widget кастомизация (persist) | ❌ Нет | Только клиентский JS, не сохраняется в БД |
| Скрипт-детектор (проверка установки виджета) | ❌ Нет | |
| Integration Hub единая страница | ❌ Нет | 3 отдельных страницы: `/admin/cliniko`, `/admin/pabau`, `/admin/channels` |
| Кросс-линковка каналов с агентами | ❌ Нет | |

## План реализации

### Этап 1: Integration Hub — единая страница и API

**Задача 1.1: Создать `admin/integrations_hub.py`**

Новый модуль вместо разрозненных `cliniko.py`, `pabau.py` + часть `pages.py`.

**API endpoints:**

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/admin/integrations` | SSR — рендерит `integrations_hub.html` |
| `GET` | `/admin/api/integrations` | Возвращает список всех интеграций со статусами |
| `POST` | `/admin/api/integrations/crm/configure` | Принимает `{provider, api_key, company_id?}` |
| `POST` | `/admin/api/integrations/crm/test` | Тест соединения |
| `POST` | `/admin/api/integrations/crm/disconnect` | Отключение CRM |
| `POST` | `/admin/api/integrations/whatsapp/configure` | Сохраняет конфиг WhatsApp |
| `POST` | `/admin/api/integrations/whatsapp/disconnect` | Отключает WhatsApp |
| `POST` | `/admin/api/integrations/widget/configure` | Сохраняет настройки виджета (цвет, позиция, приветствие) |
| `GET` | `/admin/api/integrations/widget/status` | Проверяет, активен ли скрипт на сайте клиники |
| `POST` | `/admin/api/integrations/instagram/configure` | Сохраняет токен Instagram (см. Этап 3) |
| `POST` | `/admin/api/integrations/instagram/disconnect` | Отключает Instagram |

**Структура API ответа `GET /admin/api/integrations`:**

```json
{
  "integrations": [
    {
      "id": "cliniko",
      "name": "Cliniko",
      "category": "crm",
      "status": "connected",
      "provider": "cliniko",
      "meta": {
        "shard": "eu1",
        "practitioners_count": 12,
        "services_count": 45,
        "connected_at": "2026-06-01T10:00:00Z"
      }
    },
    {
      "id": "pabau",
      "name": "Pabau",
      "category": "crm",
      "status": "not_configured",
      "meta": {}
    },
    {
      "id": "whatsapp",
      "name": "WhatsApp",
      "category": "channel",
      "status": "connected",
      "meta": {
        "phone": "+79991234567",
        "phone_number_id": "123456789"
      }
    },
    {
      "id": "instagram",
      "name": "Instagram",
      "category": "channel",
      "status": "not_configured",
      "meta": {}
    },
    {
      "id": "widget",
      "name": "Web Widget",
      "category": "channel",
      "status": "active",
      "meta": {
        "script_detected": true,
        "accent_color": "#5e6ad2",
        "position": "right"
      }
    }
  ]
}
```

**Статусы:** `not_configured`, `connected`, `error`, `active` (для виджета — отдельный `script_detected`).

**Задача 1.2: Создать `templates/integrations_hub.html`**

Одна страница вместо трёх. Карточки провайдеров, сгруппированные по категориям:
- **CRM-системы** (Cliniko, Pabau) — переключаемые
- **Каналы связи** (WhatsApp, Instagram)
- **Веб-виджет**

Каждая карточка:
- Иконка + название
- Статус-бейдж (🟢 🟡 🔴)
- Кнопка «Настроить» / «Отключить»
- При клике на карточку CRM или WhatsApp — модальное окно с пошаговым флоу

**Задача 1.3: Перенаправить старые роуты**

```
/admin/cliniko → redirect 302 → /admin/integrations
/admin/pabau   → redirect 302 → /admin/integrations
/admin/channels → redirect 302 → /admin/integrations
```

Старые модули `admin/cliniko.py`, `admin/pabau.py` удалить после верификации. Шаблоны `cliniko_connections.html`, `pabau_connections.html`, `channels.html` — удалить или оставить как fallback.

**Задача 1.4: Обновить боковое меню (`base.html`)**

Заменить отдельные пункты (Channels, Pabau, Cliniko) на один **🔌 Интеграции**.

---

### Этап 2: WhatsApp QR-код аутентификация

**Задача 2.1: Бэкенд — генерация QR-кода**

Добавить endpoint в `integrations_hub.py`:

```
POST /admin/api/integrations/whatsapp/qr
```

Возвращает `{qr_code: "data:image/png;base64,...", session_id: "..."}`.

- Использовать библиотеку `qrcode` (уже есть в зависимостях? проверить / добавить)
- Генерировать временный токен сессии, по которому фронтенд будет опрашивать статус сканирования
- При сканировании пользователь отправляет `phone_number_id`, `access_token` на внутренний callback

**Задача 2.2: Бэкенд — верификация QR-сессии**

```
GET /admin/api/integrations/whatsapp/qr/status?session_id=...
```

Возвращает `{status: "pending" | "scanned" | "confirmed" | "expired", phone?: "...", phone_number_id?: "..."}`.

**Задача 2.3: Фронтенд — отображение QR**

В модальном окне WhatsApp:
1. Шаг 1: Крупный QR-код на экране + инструкция «Откройте WhatsApp на телефоне → Меню → Связанные устройства → Привязать устройство»
2. Шаг 2: После сканирования — зелёный бейдж 🟢 `Номер +7 (999) 123-45-67 успешно привязан`
3. Шаг 3: Поле «Номера исключений» (список номеров, которые ИИ игнорирует)

**Задача 2.4: Альтернатива — ручной ввод**

Кнопка «Настроить вручную» в том же модальном окне раскрывает поля:
- `phone_number_id`
- `access_token` (с маскировкой)
- `verify_token`

**Технические заметки:**
- WhatsApp Cloud API не предоставляет OAuth QR-код как у WhatsApp Web. Реальный QR-код потребует прокси-сервера между Meta и нашей платформой. Для MVP используем ручной ввод токенов + инструкцию со скриншотами. QR-код — это имитация (генерация простого QR с ссылкой на инструкцию на русском). В будущем — интеграция с `whatsapp-business-api` через Pro-аккаунт Meta.

---

### Этап 3: Instagram Connector

**Задача 3.1: Создать `integrations/instagram.py`**

Новый модуль с классом `InstagramConnector`:

```python
class InstagramConnector:
    provider = "instagram"
    phi_safe = True

    def __init__(self, config: dict):
        self.access_token = config.get("access_token")
        self.business_page_id = config.get("business_page_id")
        self.instagram_account_id = config.get("instagram_account_id")

    async def send_message(self, recipient_id: str, text: str) -> dict:
        # POST /v22.0/{ig_account_id}/messages
        ...

    async def get_conversations(self) -> list:
        # GET /v22.0/{ig_account_id}/conversations
        ...

    async def get_profile(self, ig_user_id: str) -> dict:
        # GET /v22.0/{ig_user_id}
        ...

    def test_connection(self) -> bool:
        # GET /v22.0/{ig_account_id}?fields=name
        ...
```

Использовать `httpx` и Graph API v22.0.

**Задача 3.2: Создать `channels/instagram.py`**

Канал, аналогичный `whatsapp.py`, с вебхуком для Instagram:

```python
router = APIRouter(prefix="/channels/instagram")

@router.get("/webhook")  # Meta verification
async def verify(request: Request):
    ...

@router.post("/webhook")  # Inbound messages
async def webhook(request: Request):
    ...
```

**Задача 3.3: Добавить Instagram в `channels/registry.py`**

```python
SUPPORTED_CHANNELS = {"web_widget", "whatsapp", "instagram"}
```

**Задача 3.4: Модалка подключения Instagram**

В модальном окне:
- Шаг 1: Крупная синяя кнопка [🔵 Войти через Facebook]
  - Открывает popup с Facebook OAuth
  - После авторизации пользователь выбирает бизнес-страницу
- Шаг 2: Настройки директа:
  - [x] Отвечать в Директ (личные сообщения)
  - [ ] Отвечать на комментарии под постами
  - [ ] Реагировать на отметки в Сторис
- Шаг 3: Статус 🟢 Instagram @beauty_clinic подключён

**Технические заметки:**
- Для Instagram Business Account требуется:
  1. Facebook App с продуктом Instagram Graph API
  2. Facebook Login (OAuth) с `pages_manage_metadata`, `pages_messaging`, `instagram_basic`, `instagram_manage_messages`
  3. Webhook с подпиской на `messages` и `comments`
- В `config.py` (Settings) добавить: `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_REDIRECT_URI`
- Хранить `instagram_access_token` в `Tenant.crm_config` или в `ChannelConfig.config`

---

### Этап 4: Web Widget — персистентность настроек + скрипт-детектор

**Задача 4.1: Сохранять настройки виджета в БД**

Сейчас настройки (цвет, позиция, приветствие) генерируются на клиенте и не сохраняются. Добавить сохранение:

- `ChannelConfig.config` для `web_widget` расширяется полями:
  ```json
  {
    "title": "Jeeves support",
    "subtitle": "",
    "greeting": "Здравствуйте! Чем я могу вам помочь?",
    "accent_color": "#5e6ad2",
    "position": "right",
    "email_required": true,
    "allowed_origins": ["https://clinic.com"]
  }
  ```

**Задача 4.2: Скрипт-детектор**

Бэкенд: эндпоинт `POST /admin/api/integrations/widget/status`

Логика:
1. Берёт `allowed_origins[0]` из конфига виджета
2. Делает `GET {origin}` и ищет в HTML подстроку `<jeeves-widget`
3. Возвращает `{script_detected: true/false, checked_at: "..."}`

Фронтенд:
- На карточке виджета показывает 🟢 `Код активен на сайте clinic.com` или 🔴 `Скрипт не обнаружен на сайте`
- Зелёный индикатор обновляется раз в 5 минут (polling)
- Кнопка [📋 Скопировать код] — генерирует JS-сниппет с актуальными настройками

---

### Этап 5: Кросс-линковка Интеграции → Агенты

**Задача 5.1: Автоматически показывать подключённые каналы в настройках агента**

В `admin/agents.py` эндпоинт `GET /api/agents/{agent_id}/config` уже возвращает `channels`. Дополнить его списком доступных каналов из реестра.

**Логика:**
- В разделе Интеграции пользователь подключил Instagram
- В разделе Агенты → Входящая линия → вкладка "Каналы связи" автоматически появляется чекбокс `[x] Instagram (@beauty_clinic)`
- Пользователь включает — и агент начинает отвечать в Instagram

**API:**
- `GET /api/integrations/available` — список подключённых каналов, пригодных для привязки к агенту

**Задача 5.2: Обновить UI вкладки "Каналы" в `agent_detail.html`**

Вместо статических чекбоксов WhatsApp/Widget — динамический список из `available_channels`.

---

### Этап 6: Миграция данных и удаление старого кода

**Задача 6.1: Проверить обратную совместимость**

- Старые URL (`/admin/cliniko`, `/admin/pabau`, `/admin/channels`) — редиректы на `/admin/integrations`
- Существующие `ChannelConfig` записи в БД не трогать
- `tenant.crm_provider` и `tenant.crm_config` продолжают работать

**Задача 6.2: Удалить старые модули** (после верификации)

- `admin/cliniko.py`
- `admin/pabau.py`
- `templates/cliniko_connections.html`
- `templates/pabau_connections.html`
- `templates/channels.html`
- Из `admin/__init__.py` убрать `cliniko`, `pabau` (импорты)

---

## Схема зависимостей модулей

```
integrations_hub.py
├── integrations/cliniko.py      (сущ.)
├── integrations/pabau.py        (сущ.)
├── integrations/instagram.py    (новый)
├── channels/registry.py         (сущ. + доработка)
├── channels/whatsapp.py         (сущ.)
├── channels/instagram.py        (новый)
├── channels/widget.py           (сущ. + доработка)
├── templates/integrations_hub.html  (новый)
└── admin/agents.py              (доработка — кросс-линковка)

Изменения в main.py:
  - app.include_router(instagram_channel.router)  # новый

Изменения в config.py:
  - FACEBOOK_APP_ID, FACEBOOK_APP_SECRET, FACEBOOK_REDIRECT_URI
```

## Проверка

- `python -c "from app.main import app"` — после каждого этапа
- `pytest api/tests/ -v --tb=short` — после каждого этапа (451 тест)
- `ruff check api/app/` — после каждого этапа
- Ручная проверка: зайти в `/admin/integrations`, увидеть все карточки со статусами
- Ручная проверка: подключить CRM → статус меняется на 🟢
- Ручная проверка: скопировать код виджета → вставить на локальную HTML-страницу → скрипт-детектор показывает 🟢
- Ручная проверка: подключить Instagram → он появляется в настройках агента
