# URL & Title Validation — План доработок (v2)

## Текущие проблемы

### 1. `URL_RE` — слишком примитивный regex

**Файл:** `knowledge.html:1380`

```
/^https?:\/\/.+/i
```

| Сценарий | Результат |
|----------|-----------|
| `https://example.com` | ✅ проходит |
| `https://foo` (без TLD) | ✅ проходит |
| `https://a` | ✅ проходит |
| `https://` | ❌ не проходит (`.+` требует ≥1 символа) |
| `//example.com` (protocol-relative) | ❌ не проходит |
| `http://192.168.1.1` | ✅ проходит |
| `http://localhost:8080` | ✅ проходит |
| `ftp://example.com` | ❌ не проходит |
| `javascript:alert(1)` | ❌ не проходит |
| `https://example.com/path with spaces` | ✅ проходит (проблема — пробелы валидны) |

**Проблема:** regex не проверяет наличие домена, TLD, структуры URL. Любая строка,
начинающаяся с `http://` или `https://`, считается валидной.

---

### 2. Сервер не валидирует формат URL

**Файл:** `knowledge/__init__.py`

- `POST /urls` (line 775): проверяет только `not body.url.strip()` — любая не-пустая строка проходит
- `PATCH /urls/{id}` (line 842): вообще не проверяет — даже пустая строка обновит URL

**Разрыв между клиентом и сервером:** клиент отсекает `ftp://`, `data:`, `javascript:` и т.д.,
но сервер пропустит любые протоколы.

---

### 3. Title: клиент требует, сервер — нет

| Слой | Поведение |
|------|-----------|
| Клиент (import) | Title **required** — кнопка disabled, если пусто |
| Клиент (edit) | Title **не проверяется** — `saveEdit()` проверяет только URL |
| Сервер (POST) | `body.title or body.url` — если title пустой/None, подставляется URL |
| Сервер (PATCH) | Title обновляется без проверок |
| DB (`models.py:107`) | `title = Column(Text)` — **nullable**, может быть NULL |

**Проблема:** Discrepancy между импортом (title обязателен) и редактированием (title не проверяется).

---

### 4. `saveEdit()` — silent fail + нет try/catch

**Файл:** `knowledge.html:1587`

```javascript
if (!newUrl || !URL_RE.test(newUrl)) return;  // return без toast, без ошибки
await api(...);                                // нет try/catch — unhandled rejection
```

Пользователь не получает обратной связи — кнопка просто не срабатывает, а при ошибке
сети/сервера — unhandled promise rejection.

---

### 5. Дубликаты URL — неполная нормализация

**Файл:** `knowledge/__init__.py:788-802`

Сравнение `url == body.url` — прямое строковое сравнение без:
- trim с обоих сторон
- trailing slash (`/` vs без `/`)
- protocol (`http://` vs `https://`)
- www (`www.example.com` vs `example.com`)
- нижний регистр

`https://Example.com/Path` и `https://example.com/path` считаются разными URL.

Дополнительно: `POST /urls` при дубликате возвращает **200** вместо 409 — это код-смэлл
(нарушение семантики HTTP для REST API).

---

### 6. Нет ограничений на длину полей

`URL_RE` не ограничивает длину. DB использует `Text` (безлимитный).
Нет `max_length` на Pydantic-моделях. Можно отправить URL длиной 100KB.

---

## План доработок

### A. Client-side URL validation (использовать `new URL()` вместо regex)

Заменить `URL_RE` и все проверки на нативный `URL()` конструктор:

```javascript
// Удалить: const URL_RE = /^https?:\/\/.+/i;

function isValidUrl(str) {
  if (!str || typeof str !== 'string') return false;
  try {
    var u = new URL(str);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch(e) {
    return false;
  }
}
```

**Почему это лучше regex:**
- Валидирует полную структуру URL (домен, путь, query, фрагменты)
- Поддерживает IDN (интернациональные домены — кириллица, иероглифы и т.д.)
- Поддерживает IPv6 (`https://[::1]:8080/path`)
- Поддерживает auth (`https://user:pass@example.com`)
- Пробелы в URL невалидны (выбрасывает TypeError)
- Не нужно поддерживать и отлаживать сложный regex (95+ символов)

**Изменяемые функции:**

```javascript
function validateUrlInput() {
  var urlEl = document.getElementById('wpUrlInput');
  var titleEl = document.getElementById('wpTitleInput');
  var url = urlEl.value.trim();
  var title = titleEl.value.trim();
  // Показывать err-класс, только если поле не пустое И URL невалидный
  urlEl.className = 'kb-input' + (url && !isValidUrl(url) ? ' err' : '');
  document.getElementById('wpImportBtn').disabled = !url || !title || !isValidUrl(url);
}

async function importWebPage() {
  if (_importing) return;
  var url = document.getElementById('wpUrlInput').value.trim();
  var title = document.getElementById('wpTitleInput').value.trim();
  if (!url) return showToast('URL is required', 'err');
  if (!isValidUrl(url)) return showToast('URL must start with http:// or https://', 'err');
  if (!title) return showToast('Title is required', 'err');
  // ... остальное без изменений
}

async function saveEdit(id) {
  var newUrl = document.getElementById('edit-url-' + id).value.trim();
  var newTitle = document.getElementById('edit-title-' + id).value.trim();
  if (!newUrl || !isValidUrl(newUrl)) {
    showToast('URL must start with http:// or https://', 'err');
    return;
  }
  if (!newTitle) {
    showToast('Title is required', 'err');
    return;
  }
  try {
    await api('/knowledge/urls/' + id, { method: 'PATCH', body: { url: newUrl, title: newTitle } });
    loadWebPages();
  } catch(e) {
    showToast(e.message, 'err');
  }
}
```

---

### B. Server-side URL validation (Pydantic v2 `@field_validator`)

Добавить валидатор на `_UrlImportIn`:

```python
import re
from urllib.parse import urlparse
from pydantic import BaseModel, field_validator

class _UrlImportIn(BaseModel):
    url: str
    title: str | None = None
    folder_id: uuid.UUID | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("URL is required")
        if len(v) > 2048:
            raise ValueError("URL must not exceed 2048 characters")
        if not re.match(r"https?://", v, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("Invalid URL: missing hostname")
        return v
```

Аналогичный валидатор для `_UrlUpdateBody` — но с учётом `url: str | None` (пропускать,
если None):

```python
class _UrlUpdateBody(BaseModel):
    url: str | None = None
    title: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("URL is required")
        if len(v) > 2048:
            raise ValueError("URL must not exceed 2048 characters")
        if not re.match(r"https?://", v, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("Invalid URL: missing hostname")
        return v
```

После добавления валидатора удалить ручную проверку `if not body.url.strip(): raise HTTPException(400, "url is required")` на строке 775 — она становится избыточной (Pydantic вернёт 422).

**Важно:** FastAPI/Pydantic v2 возвращает `422 Unprocessable Entity` с деталями ошибки.  
Поле `msg` будет вида `"Value error: URL must start with http:// or https://"`.
На клиенте `e.message` будет содержать эту строку — тост с ошибкой будет
информативным.

---

### C. Title validation — синхронизация клиента и сервера

- **Клиент (edit):** добавить проверку title в `saveEdit()` — см. секцию D
- **Сервер (POST):** оставить title опциональным (fallback `body.title or body.url`) — разумно
- **Сервер (PATCH):** если title передан пустой строкой — не обновлять, оставить старое значение
- **DB:** оставить nullable (обратная совместимость с существующими записями)

---

### D. Edit mode — полный cycle фидбека

`saveEdit()` должен:
1. Валидировать URL (isValidUrl) — toast `err` при невалидном
2. Валидировать title (не пустой) — toast `err` при пустом
3. Оборачивать `api()` в try/catch — toast с сообщением ошибки
4. При успехе — `loadWebPages()` (перегружает таблицу + очищает edit mode)

```javascript
// Полная реализация — см. секцию A
```

---

### E. Duplicate detection — нормализация URL

**Проблема с `func.lower()` в SQL:** `func.lower(KnowledgeUrl.url)` не использует
обычный индекс на колонке `url`. Для продакшена с тысячами URL потребуется
функциональный индекс.

**Решение в два этапа:**

1. **Python-нормализация перед запросом + comparison в Python:**

```python
def _normalize_url(url: str) -> str:
    """Нормализует URL для сравнения дубликатов."""
    url = url.strip().lower().rstrip("/")
    return url

# В дубликат-чеке (lines 788-802):
normalized = _normalize_url(body.url)
existing = db.execute(
    select(KnowledgeUrl).where(
        KnowledgeUrl.tenant_id == tenant.id,
        KnowledgeUrl.status != "failed",
    )
).scalars().all()
existing = [r for r in existing if _normalize_url(r.url) == normalized]
if existing:
    rec = existing[0]
    return {
        "id": str(rec.id),
        "url": rec.url,
        "title": rec.title,
        "status": rec.status,
        "duplicate": True,
    }
```

Для продакшена — добавить колонку `url_normalized` с уникальным индексом:

```python
# models.py:
url_normalized = Column(Text, nullable=True)  # unique index будет добавлен
```

и миграцию Alembic для её заполнения.

2. **HTTP status для дубликата:** изменить `return {...}` на `raise HTTPException(409, "URL already exists")` или оставить 200 с `"duplicate": True` (требует согласования — breaking change для клиента).

---

### F. Max length constraints

- Pydantic: `url: str = Field(max_length=2048)`, `title: str | None = Field(None, max_length=512)`
- DB: оставить `Text` (миграция не требуется)
- Client: добавить проверку длины в `validateUrlInput()`:

```javascript
function validateUrlInput() {
  var urlEl = document.getElementById('wpUrlInput');
  var titleEl = document.getElementById('wpTitleInput');
  var url = urlEl.value.trim();
  var title = titleEl.value.trim();
  var urlErr = url && !isValidUrl(url);
  var titleErr = title.length > 512;
  urlEl.className = 'kb-input' + (urlErr ? ' err' : '');
  document.getElementById('wpImportBtn').disabled = !url || !title || urlErr || titleErr;
}
```

---

## Приоритет

| # | Задача | Приоритет | Сложность | Зависимости |
|---|--------|-----------|-----------|-------------|
| A | Client-side `new URL()` вместо regex | high | low | — |
| B | Server-side Pydantic валидатор | high | medium | — |
| C | Title validation в edit mode | high | low | A |
| D | saveEdit() toast + try/catch | high | low | A |
| E | Duplicate normalization | medium | medium | — |
| F | Max length constraints | low | low | — |

---

## Изменяемые файлы

| Файл | Изменения |
|------|-----------|
| `api/app/templates/knowledge.html` | Удалить `URL_RE`, добавить `isValidUrl()`, обновить `validateUrlInput()`, `importWebPage()`, `saveEdit()` |
| `api/app/knowledge/__init__.py` | Добавить `import re`, `from urllib.parse import urlparse`, `from pydantic import field_validator`; добавить валидаторы на `_UrlImportIn` и `_UrlUpdateBody`; удалить ручную проверку line 775; обновить duplicate detection |

---

## Тест-кейсы для проверки

### Импорт
| URL | Title | Ожидание |
|-----|-------|----------|
| `""` | `"Test"` | ❌ URL is required |
| `"not-a-url"` | `"Test"` | ❌ must start with http:// |
| `"ftp://example.com"` | `"Test"` | ❌ must start with http:// |
| `"https://"` | `"Test"` | ❌ missing hostname |
| `"https://example.com"` | `""` | ❌ Title is required |
| `"https://example.com"` | `"Test"` | ✅ |
| `"  https://example.com  "` | `"Test"` | ✅ (trim) |
| `"https://example.com/path with spaces"` | `"Test"` | ❌ пробелы невалидны |

### Редактирование
| URL | Title | Ожидание |
|-----|-------|----------|
| `"https://example.com"` | `""` | ❌ Title required (с toast) |
| `""` | `"New title"` | ❌ URL required (с toast) |
| `"https://other.com"` | `"Valid"` | ✅ |
| `"javascript:alert(1)"` | `"Test"` | ❌ must start with http:// |

### Дубликаты
| Import 1 | Import 2 | Ожидание |
|----------|----------|----------|
| `https://example.com/Path` | `https://example.com/path` | duplicate |
| `https://example.com/` | `https://example.com` | duplicate |
| `https://Example.COM` | `https://example.com` | duplicate |

### Edge cases (new URL())
| URL | Ожидание |
|-----|----------|
| `http://localhost:8080` | ✅ |
| `http://127.0.0.1:3000/path` | ✅ |
| `https://user:pass@example.com` | ✅ |
| `https://[::1]:8080/path` | ✅ |
| `https://домен.рф` | ✅ (IDN — new URL() корректно парсит) |
| `https://example.com?a=1&b=2` | ✅ |
| `https://example.com#fragment` | ✅ |

---

## Критические упущения v1 → v2

1. **Section A:** Предложенный regex `^https?:\/\/[a-z0-9]([...])*(\.[a-z]{2,}|...)` **сломан** — группа `(\.[a-z0-9](...))*` жадно съедает `.com` как промежуточный лейбл, не оставляя ничего для TLD-части. `https://example.com` не пройдёт. *Решение: использовать `new URL()` вместо regex.*

2. **Section B:** Не хватало `import re` и `from urllib.parse import urlparse` в списке изменяемых импортов.

3. **Section B:** `field_validator` должен обрабатывать `str | None` для `_UrlUpdateBody` (в PATCH url опционален).

4. **Section E:** `func.lower(KnowledgeUrl.url)` не использует обычный B-tree индекс. Для тысяч записей нужен функциональный индекс или отдельная колонка `url_normalized`.

5. **Section E:** `POST /urls` возвращает 200 для дубликата — код-смэлл. Добавлено примечание про 409 Conflict.

6. **Missing:** После добавления Pydantic-валидатора ручная проверка `not body.url.strip()` на line 775 становится избыточной — её нужно удалить.

7. **Missing:** IDN‑домены (кириллица, иероглифы) — regex их не поддерживает, `new URL()` поддерживает. Упомянуто в тест-кейсах.
