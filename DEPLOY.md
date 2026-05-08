# Jeeves — Как устроен проект и деплой

## Что такое Jeeves простыми словами

Jeeves — это AI-ассистент для поддержки клиентов. Чат-бот на сайте, который:
- Знает ответы из загруженных документов (инструкции, FAQ, прайсы)
- Видит данные клиента из CRM (тариф, история)
- Может менять тариф или создать тикет через HTTP-действия
- Если не знает — переводит на человека

Встраивается на любой сайт одной строчкой кода.

---

## Стек технологий

| Что | Зачем |
|-----|-------|
| **Python 3.13** | Основной язык |
| **FastAPI + Uvicorn** | Веб-сервер, автоматическая OpenAPI документация |
| **PostgreSQL 15** | Главная база: тенанты, логи, конфиги |
| **ChromaDB** | Векторный поиск по документам |
| **OpenAI (GPT-4o-mini)** | Мозг агента |
| **SQLAlchemy** | ORM для работы с базой |
| **Alembic** | Миграции базы данных |
| **Pydantic** | Валидация запросов/ответов |
| **bcrypt + PyJWT** | Хеширование паролей, JWT-токены |

**Фронтенд:**
- `widget.js` — встраиваемый чат-виджет (чистый JS, Shadow DOM)
- `dashboard.js` — админ-панель (vanilla JS)

**Инфраструктура:**
- **Docker** — контейнеризация
- **Railway** — хостинг с авто-деплоем из GitHub

---

## Структура проекта

```
Jeeves/
├── Dockerfile              # Сборка всего (api + frontend)
├── api/
│   ├── app/
│   │   ├── main.py         # Точка входа, Alembic миграции
│   │   ├── agent.py        # Агент: RAG + CRM + инструменты
│   │   ├── rag.py          # ChromaDB: индексация и поиск
│   │   ├── memory.py       # Память разговоров
│   │   ├── models.py       # ORM-модели
│   │   ├── channels/       # Widget, Telegram, WhatsApp
│   │   ├── crm.py          # REST-коннектор к CRM
│   │   ├── templates/      # HTML админки
│   │   └── ...
│   ├── alembic/            # Миграции базы
│   ├── tests/              # Тесты
│   └── requirements.txt
├── frontend/
│   ├── widget.js           # Чат-виджет
│   ├── dashboard.js        # JS админки
│   └── dashboard.css
├── knowledge/              # Файлы KB (не в git)
├── config.yaml             # Промпты, настройки модели
└── scripts/
    └── test_api.sh
```

---

## Путь одного сообщения

```
Клиент пишет в виджет
  │
  ▼
/v1/widget/chat — API принимает сообщение
  │
  ├─► RAG ищет в ChromaDB похожие фрагменты
  ├─► CRM читает данные клиента
  ├─► Agent собирает: промпт + история + контекст → OpenAI
  │
  ▼
OpenAI возвращает ответ (может вызвать инструмент)
  │
  ▼
API сохраняет в базу → возвращает клиенту → виджет показывает
```

---

## Деплой на Railway

### Архитектура в продакшене

```
┌──────────────────────────────────────────┐
│           Railway (production)            │
│                                           │
│  ┌──────────────┐   ┌─────────────────┐  │
│  │  API Service │   │  PostgreSQL     │  │
│  │  FastAPI     │◄─►│  Railway managed│  │
│  │  Uvicorn     │   │                 │  │
│  └──────┬───────┘   └─────────────────┘  │
│         │                                 │
│  ┌──────┴───────┐                         │
│  │ Chroma vol.  │  Persistent Disk         │
│  │ /data/chroma │  переживает деплои       │
│  └──────────────┘                         │
└──────────────────────────────────────────┘
```

### Настройка Railway

**1. Создай проект**
- Зайди на [railway.app](https://railway.app) → Sign in через GitHub
- New Project → Deploy from GitHub repo → выбери свой репозиторий

**2. Добавь PostgreSQL**
- В проекте → New → Database → PostgreSQL
- Railway создаст базу и подставит `DATABASE_URL`

**3. Подключи Persistent Volume для ChromaDB**
- В API Service → Volumes → Add Volume
  - Mount Path: `/data/chroma`
  - Size: 1GB
- Добавь переменную: `CHROMA_PATH=/data/chroma`

**4. Переменные окружения**

| Key | Value |
|-----|-------|
| `DATABASE_URL` | Railway подставляет сам |
| `OPENAI_API_KEY` | `sk-...` |
| `JWT_SECRET` | случайная строка 32+ символов |
| `CHROMA_PATH` | `/data/chroma` |
| `PUBLIC_BASE_URL` | твой Railway домен |

**5. Push → авто-деплой**
```
git push → Railway собирает Docker → деплоит ~2-3 мин
```

---

## Локальная разработка

### Что нужно
1. **Python 3.13**
2. **PostgreSQL** (локально или Docker)
3. **.env файл** в `api/`:

```env
DATABASE_URL=postgresql+psycopg2://jeeves:jeeves123@localhost:5432/jeeves
OPENAI_API_KEY=sk-your-key-here
JWT_SECRET=any-random-string-at-least-32-characters
CHROMA_PATH=./chroma_data
```

### Запуск
```bash
cd api
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Что открылось
- **Админка:** http://localhost:8000/admin
- **API документация:** http://localhost:8000/docs
- **Виджет:** http://localhost:8000/widget.js

---

## Деплой при изменении кода

```
git add . && git commit -m "описание" && git push
                                           │
                                           ▼
                              Railway видит push
                              Собирает Docker-образ
                              Запускает новую версию
                              Миграции БД (Alembic)
                              Готово ~2-3 минуты
```

**Rollback:** Railway Dashboard → Deployments → выбери предыдущий → Rollback.

---

## Данные и хранилище

| Что | Где | Переживает деплой? |
|-----|-----|-------------------|
| PostgreSQL | Railway managed | ✅ |
| ChromaDB | Persistent Volume `/data/chroma` | ✅ |
| Загруженные файлы | Ephemeral файловая система | ❌ (удаляется при деплое) |

> **Важно:** файлы в Knowledge Base удаляются при перезапуске. Это не критично — эмбеддинги уже в ChromaDB. Если нужен полный ре-индекс, файлы придётся загрузить заново. В будущем — S3.

---

## Миграции базы данных

Alembic запускается автоматически при старте API.

Для создания новой миграции:
```bash
cd api
alembic revision --autogenerate -m "описание"
```

---

## Лимиты и биллинг

MVP-заглушка:
- **100 диалогов** на тенант (счётчик `dialogs_used`)
- **14 дней** trial с момента регистрации
- После превышения — API возвращает **402 Payment Required**

План полностью захардкожен как `"free"`. Stripe-интеграция запланирована.

---

## Логирование

Используется Python `logging` с форматом: `%(asctime)s %(levelname)s %(name)s :: %(message)s`.

Все внешние вызовы (OpenAI, CRM, вебхуки) логируются с `WARNING` при ошибках и имеют `timeout=30s`.

---

## Мониторинг

### Railway Dashboard
- **Logs** — вывод в реальном времени
- **Deployments** — история, rollback
- **Metrics** — CPU, RAM, трафик

### Проверка здоровья
```bash
curl https://твой-домен.up.railway.app/health
```

### Rollback
Railway Dashboard → Deployments → предыдущий → Rollback (~30 сек).

---

## Частые проблемы

**«Build failed на Railway»**
→ Вкладка Logs в Deployment. Обычно — нет зависимости в `requirements.txt` или ошибка в Dockerfile.

**«API не подключается к базе»**
→ Проверь `DATABASE_URL` в Variables. Railway обычно подставляет сам.

**«ChromaDB теряет данные после деплоя»**
→ Убедись что Persistent Volume подключен в Volumes и `CHROMA_PATH` указывает на него.

**«Widget не показывает ответы»**
→ Проверь `PUBLIC_BASE_URL`. Должен быть Railway домен, не localhost.

**«503 Service Unavailable»**
→ Railway free tier засыпает при неактивности. Первый запрос после сна — 30-60 секунд.

---

## Чек-лист для продакшена

- [x] PostgreSQL — Railway managed
- [x] API — Dockerfile, авто-деплой
- [x] ChromaDB — Persistent Volume
- [x] Alembic миграции
- [x] API versioning `/v1/`
- [ ] Knowledge files — S3 для persistency
- [ ] Stripe billing
- [ ] Redis production (rate limiting, memory)
- [ ] Мониторинг — алерты
- [ ] S3/Object Storage для файлов
