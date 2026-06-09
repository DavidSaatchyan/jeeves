# Knowledge Base — "Web Pages" Tab

**Выделить URL/веб-страницы из общего раздела Documents в отдельный таб.**

---

## 1. Зачем

Сейчас импортированные URL смешаны с загруженными файлами в одном табе "Documents". Это плохо потому что:

| Аспект | Documents (файлы) | Web Pages (URL) |
|--------|------------------|-----------------|
| Жизненный цикл | Статичны — загрузил и забыл | Могут устаревать — контент на сайте меняется |
| Действия | Upload, Delete, Edit content | Import, Refresh, Delete, Track staleness |
| Статусы | processing → ready / failed | pending → processing → ready / failed |
| Метаданные | filename, size_bytes, file_type | URL, title, last_fetched_at, content_hash |
| Источник | Пользователь загружает файл | Внешний сайт — фетчится бэкендом |
| Типичный юзкейс | Загрузить PDF протокола | Импортировать страницу с дозировками |

**Решение:** Новый таб "Web Pages" с собственной таблицей, импортом и управлением жизненным циклом. Documents остаётся только для файлов.

---

## 2. Use Cases & Scenarios

### 2.1 Импорт URL

**Actor:** Администратор клиники

```
1. Admin открывает Knowledge → таб "Web Pages"
2. Видит таблицу всех импортированных URL + inline import bar
3. Вводит URL (начинается с http/https) + опциональный title + папку
4. Жмёт "Import"
5. Валидация на фронтенде: URL обязателен, должен быть http/https
6. URL появляется в таблице со статусом "processing"
7. Через несколько секунд статус → "ready" (зелёный)
8. Контент страницы проиндексирован и доступен для поиска агентами
```

### 2.2 Редактирование URL

**Actor:** Администратор клиники

```
1. Admin жмёт иконку редактирования напротив URL
2. URL и title становятся редактируемыми (inline edit)
3. Меняет URL или title
4. Жмёт "Save" → бэкенд обновляет запись
5. Если URL изменён — запускается переиндексация (refresh)
6. Статус → "processing" → "ready"
```

### 2.3 Обновление устаревшего URL

**Actor:** Администратор клиники

```
1. Admin видит в таблице URL со статусом "stale" (желтый) — не обновлялся >72h
2. Жмёт кнопку "Refresh" напротив URL
3. Статус → "processing"
4. Бэкенд фетчит URL, сравнивает content_hash
5. Если изменился → переиндексация, статус → "ready"
6. Если не изменился → статус → "ready", last_fetched_at обновлён
7. Admin видит обновлённую дату в колонке "Last fetched"
```

### 2.4 Массовое обновление

**Actor:** Администратор клиники

```
1. Admin видит кнопку "Refresh all stale" (активна когда есть stale URL)
2. Жмёт — все stale URL становятся "processing"
3. Каждый URL обновляется последовательно (batch)
4. Таблица обновляется в реальном времени через polling
```

### 2.5 Удаление URL

**Actor:** Администратор клиники

```
1. Admin жмёт иконку корзины напротив URL
2. Появляется confirm modal: "Delete this web page? Chunks will be removed from the knowledge base."
3. Подтверждает → URL удалён из таблицы, chunks удалены из Chroma
```

### 2.6 Повтор неудачного импорта

**Actor:** Администратор клиники

```
1. Admin видит URL со статусом "failed" (красный) + текст ошибки в тултипе
2. Жмёт "Retry" → статус → "processing"
3. Бэкенд перефетчит URL заново
4. Если успех → "ready", если снова ошибка → "failed" с обновлённой ошибкой
```

### 2.7 Просмотр содержимого URL

**Actor:** Администратор клиники (проверка качества)

```
1. Admin жмёт на URL в таблице → открывается chunk viewer
2. Видит заголовок страницы, структуру (headings), количество chunks
3. Может просмотреть каждый chunk с текстом
```

---

## 3. UX/UI Design

### 3.1 Структура страницы Knowledge

Текущая структура:
```
┌─ Knowledge ──────────────────────────────────────┐
│  [Documents]  [Practice/HMS Data]                 │
│                                                    │
│  ┌─ Documents tab ───────────────────────────────┐│
│  │  Upload modal: [File] [Import URL]  ← buried  ││
│  │  Table: files + URLs mixed                    ││
│  └───────────────────────────────────────────────┘│
└────────────────────────────────────────────────────┘
```

Новая структура:
```
┌─ Knowledge ──────────────────────────────────────┐
│  [Documents]  [Web Pages]  [Practice/HMS Data]    │
│                                                    │
│  ┌─ Web Pages tab ───────────────────────────────┐│
│  │  ┌─ Import bar ──────────────────────────────┐││
│  │  │  [URL input] [Title input] [Import →]     │││
│  │  └───────────────────────────────────────────┘││
│  │  ┌─ Stale alert ────────────────────────────┐ ││
│  │  │  ⚠ 3 URLs haven't been refreshed in      │ ││
│  │  │  over 72 hours. [Refresh all stale]       │ ││
│  │  └───────────────────────────────────────────┘ ││
│  │  ┌─ URL table ───────────────────────────────┐││
│  │  │  URL │ Title │ Folder │ Status │ Fetched  │││
│  │  │  ... │ ...   │ ...    │ ● ready│ 2h ago   │││
│  │  │  ... │ ...   │ ...    │ ● stale│ 5d ago   │││
│  │  └───────────────────────────────────────────┘││
│  └───────────────────────────────────────────────┘│
└────────────────────────────────────────────────────┘
```

### 3.2 Tab bar

```html
<!-- knowledge.html — currently 2 tabs, now 3 -->
<div class="kb-tabs">
  <button class="kb-tab" data-tab="documents">Documents</button>
  <button class="kb-tab active" data-tab="webpages">Web Pages</button>
  <button class="kb-tab" data-tab="practice">Practice / HMS Data</button>
</div>
```

### 3.3 Import bar (inline, not modal)

```html
<div id="webpages-import-bar" class="import-bar">
  <div class="import-bar-row">
    <input type="url" id="wpUrlInput" placeholder="https://example.com/clinic-policies"
           class="kb-input flex-2" oninput="validateUrlInput()" />
    <input type="text" id="wpTitleInput" placeholder="Page title (optional)" class="kb-input flex-1" />
    <select id="wpFolderSelect" class="kb-input">
      <option value="">No folder</option>
      <!-- rendered folders -->
    </select>
    <button onclick="importWebPage()" class="btn accent" id="wpImportBtn">
      <span class="btn-icon">↗</span> Import
    </button>
  </div>
  <div id="wpImportResult" class="import-result" style="display:none"></div>
</div>
```

**Почему inline, а не modal:**
- Import URL — быстрое действие (ввести URL + title)
- Не нужно открывать modal, переключать табы внутри modal'а
- Результат (success/error) показывается прямо под строкой ввода
- Улучшает discoverability — кнопка всегда видна
- Валидация URL в реальном времени (подсветка красным если не http/https)

### 3.4 Stale alert

```html
<div id="staleAlert" class="alert warn" style="display:none">
  <span class="alert-icon">⚡</span>
  <span id="staleCount">3</span> web pages haven't been refreshed in over 72 hours.
  <button onclick="refreshAllStale()" class="btn sm accent">Refresh all stale</button>
  <button onclick="document.getElementById('staleAlert').style.display='none'" class="ghost sm">Dismiss</button>
</div>
```

**States:**
| State | Shows when |
|-------|-----------|
| Visible + warn | `stale_count > 0` (из `updateStaleAlert(count)`) |
| Hidden | `stale_count === 0` or dismissed |
| Processing | During batch refresh — spinner replaces button |

### 3.5 URL table

```html
<table class="kb-table" id="wpTable">
  <thead>
    <tr>
      <th class="col-url">URL</th>
      <th class="col-title">Title</th>
      <th class="col-folder">Folder</th>
      <th class="col-status">Status</th>
      <th class="col-chunks">Chunks</th>
      <th class="col-fetched">Last fetched</th>
      <th class="col-actions">Actions</th>
    </tr>
  </thead>
  <tbody id="wpBody">
    <!-- rendered by JS -->
  </tbody>
</table>
```

**Row statuses:**

| Status | Pill | Actions available |
|--------|------|------------------|
| `ready` | `.pill.ok` | Refresh, Edit, Delete, View chunks |
| `stale` | `.pill.warn` | Refresh, Edit, Delete, View chunks |
| `processing` | `.pill` with spinner | — |
| `pending` | `.pill.muted` | Delete |
| `failed` | `.pill.err` | Retry, Edit, Delete |

**Last fetched display:**
```javascript
function timeAgo(date) {
  const diff = Date.now() - new Date(date).getTime();
  if (diff < 3600000) return `${Math.floor(diff/60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff/3600000)}h ago`;
  return `${Math.floor(diff/86400000)}d ago`;
}
```

### 3.6 State machine

```
                    ┌──────────┐
                    │  pending  │  ← только что импортирован
                    └────┬─────┘
                         │ background fetch
                         ▼
                    ┌──────────┐
              ┌─────│ processing│─────┐
              │     └─────┬────┘     │
              │           │          │
              ▼           ▼          ▼
         ┌────────┐ ┌────────┐ ┌────────┐
         │ ready  │ │ stale  │ │ failed │
         └───┬────┘ └───┬────┘ └───┬────┘
             │          │          │
             │ refresh  │ refresh  │ retry
             └─────┬────┘          │
                   ▼               │
              processing ←─────────┘
```

### 3.7 Loading state

```html
<div id="wpLoading" class="skel-card" style="display:none">
  <div class="skel-shimmer" style="height:40px; margin-bottom:8px;"></div>
  <div class="skel-shimmer" style="height:40px; margin-bottom:8px; width:80%;"></div>
  <div class="skel-shimmer" style="height:40px; width:60%;"></div>
</div>
```

### 3.8 Empty state

```html
<div id="wpEmpty" class="empty-state" style="display:none">
  <div class="empty-state-icon">🌐</div>
  <div class="empty-state-title">No web pages imported</div>
  <div class="empty-state-desc">
    Import clinic policies, dosage guidelines, or protocol pages from the web.
    Agents will use this content to answer patient questions.
  </div>
</div>
```

### 3.9 Documents tab changes

После выделения URL в отдельный таб, Documents tab:
- Убирается "Import URL" из upload modal — остаётся только "File"
- Таблица показывает только `FileRecord` (type="document"), не `KnowledgeUrl`
- Summary bar: только файлы (без URL counts)
- Upload modal: только drag-drop / browse for .txt/.pdf/.md

### 3.10 Folder interaction

**Решения:**
- Folders — общие для файлов и URL (одно и то же дерево)
- В табе Web Pages показываются все папки, но фильтр применяется к URL
- Folder dropdown в import bar позволяет сразу положить URL в папку
- Folder filter в шапке таблицы (как сейчас в Documents)

---

## 4. Technical Implementation

### 4.1 API — что уже есть

Весь API уже существует, менять не нужно:

| Endpoint | Method | Используется для |
|----------|--------|-----------------|
| `/knowledge/urls` | GET | Список всех URL (уже фильтрует по folder_id query param) |
| `/knowledge/urls` | POST | Импорт нового URL |
| `/knowledge/urls/{id}` | DELETE | Удаление URL |
| `/knowledge/urls/stale` | GET | Список stale URL (`?max_age_hours=72`) |
| `/knowledge/urls/{id}/refresh` | POST | Refresh конкретного URL |
| `/knowledge/urls/{id}/chunks` | GET | Просмотр chunks URL |
| `/knowledge/folders` | GET | Список папок |

### 4.2 Новые API endpoints

#### PATCH `/knowledge/urls/{id}` — редактирование URL/title

```python
@router.patch("/urls/{url_id}")
def update_url(
    url_id: UUID,
    body: _UrlUpdateBody,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    url = db.get(KnowledgeUrl, url_id)
    if not url or url.tenant_id != tenant.id:
        raise HTTPException(404)
    changed = False
    if body.url and body.url != url.url:
        url.url = body.url
        changed = True
    if body.title is not None and body.title != url.title:
        url.title = body.title
    db.commit()
    if changed:
        # URL changed — re-fetch and re-index
        asyncio.create_task(_background_index_url(url.id))
    return {"ok": True}
```

```python
class _UrlUpdateBody(BaseModel):
    url: str | None = None
    title: str | None = None
```

#### POST `/knowledge/urls/refresh-stale` — массовое обновление

```python
@router.post("/urls/refresh-stale")
def refresh_all_stale(
    max_age_hours: int = Query(72),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Refresh all stale URLs for this tenant."""
    stale = db.execute(
        select(KnowledgeUrl).where(
            KnowledgeUrl.tenant_id == tenant.id,
            KnowledgeUrl.status == "ready",
            KnowledgeUrl.last_fetched_at < datetime.utcnow() - timedelta(hours=max_age_hours),
        )
    ).scalars().all()
    for url in stale:
        url.status = "processing"
    db.commit()
    for url in stale:
        asyncio.create_task(_background_index_url(url.id))
    return {"refreshed": len(stale)}
```

### 4.3 Template changes: `knowledge.html`

**Changes needed:**

| # | Change | Location | Complexity |
|---|--------|----------|-----------|
| 1 | Add tab button "Web Pages" | kb-tabs div | low |
| 2 | Add tab panel `#webpages-panel` | after `#practice-panel` | medium |
| 3 | Add import bar HTML | in `#webpages-panel` | low |
| 4 | Add stale alert HTML | in `#webpages-panel` | low |
| 5 | Add URL table HTML | in `#webpages-panel` | low |
| 6 | Add empty state HTML | in `#webpages-panel` | low |
| 7 | Remove Import URL from upload modal | `#uploadModal` | low |
| 8 | Update `openTab()` to handle 3rd tab | kb-tabs JS | low |
| 9 | Add `loadWebPages()` function | JS section | medium |
| 10 | Add `importWebPage()` function | JS section | medium |
| 11 | Add `refreshWebPage(id)` function | JS section | low |
| 12 | Add `refreshAllStale()` function | JS section | low |
| 13 | Add `deleteWebPage(id)` function | JS section | low |
| 14 | Update summary stats for Documents tab | JS section | low |
| 15 | Add stale polling (check every 30s) | JS section | low |

**Total template changes:** ~200 lines added, ~30 lines removed.

### 4.4 JS function stubs

```javascript
// === Web Pages Tab ===

// ── URL validation ──
const URL_RE = /^https?:\/\/.+/i;
function validateUrlInput() {
  const el = document.getElementById('wpUrlInput');
  const val = el.value.trim();
  if (val && !URL_RE.test(val)) {
    el.className = 'kb-input flex-2 err';
  } else {
    el.className = 'kb-input flex-2';
  }
}

// ── Loading state ──
function showTableLoading(show) {
  document.getElementById('wpLoading').style.display = show ? 'block' : 'none';
  document.getElementById('wpBody').style.display = show ? 'none' : '';
  document.getElementById('wpEmpty').style.display = 'none';
}

// ── Load table ──
async function loadWebPages(folderId) {
  showTableLoading(true);
  try {
    const data = await api('/knowledge/urls' + (folderId ? `?folder_id=${folderId}` : ''));
    const staleData = await api('/knowledge/urls/stale');
    renderTable(data.urls || []);
    updateStaleAlert(staleData.stale_urls?.length || 0);
  } catch (e) {
    document.getElementById('wpBody').innerHTML =
      `<tr><td colspan="7" class="err-cell">Error: ${e.message}</td></tr>`;
  } finally {
    showTableLoading(false);
  }
}

// ── Import ──
let _importing = false;  // throttling
async function importWebPage() {
  if (_importing) return;
  const url = document.getElementById('wpUrlInput').value.trim();
  const title = document.getElementById('wpTitleInput').value.trim();
  const folderId = document.getElementById('wpFolderSelect').value;
  if (!url) return showResult('wpImportResult', 'URL is required', 'err');
  if (!URL_RE.test(url)) return showResult('wpImportResult', 'URL must start with http:// or https://', 'err');
  _importing = true;
  document.getElementById('wpImportBtn').disabled = true;
  try {
    await api('/knowledge/urls', {
      method: 'POST',
      body: JSON.stringify({ url, title, folder_id: folderId || null }),
    });
    showResult('wpImportResult', 'Imported ✓', 'ok');
    document.getElementById('wpUrlInput').value = '';
    document.getElementById('wpTitleInput').value = '';
    loadWebPages(currentFolderId);
  } catch (e) {
    showResult('wpImportResult', e.message, 'err');
  } finally {
    _importing = false;
    document.getElementById('wpImportBtn').disabled = false;
  }
}

// ── Edit (inline) ──
async function editWebPage(id) {
  const row = document.querySelector(`tr[data-url-id="${id}"]`);
  const urlCell = row.querySelector('.col-url-val');
  const titleCell = row.querySelector('.col-title-val');
  const currentUrl = urlCell.textContent;
  const currentTitle = titleCell.textContent;
  urlCell.innerHTML = `<input type="url" class="kb-input" value="${esc(currentUrl)}" id="edit-url-${id}" />`;
  titleCell.innerHTML = `<input type="text" class="kb-input" value="${esc(currentTitle)}" id="edit-title-${id}" />`;
  row.querySelector('.col-actions').innerHTML =
    `<button onclick="saveEdit('${id}')" class="btn sm accent">Save</button>
     <button onclick="loadWebPages(currentFolderId)" class="btn sm ghost">Cancel</button>`;
}

async function saveEdit(id) {
  const newUrl = document.getElementById(`edit-url-${id}`).value.trim();
  const newTitle = document.getElementById(`edit-title-${id}`).value.trim();
  if (!newUrl || !URL_RE.test(newUrl)) return;
  await api(`/knowledge/urls/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ url: newUrl, title: newTitle }),
  });
  loadWebPages(currentFolderId);
}

// ── Refresh ──
async function refreshWebPage(id) {
  await api(`/knowledge/urls/${id}/refresh`, { method: 'POST' });
  loadWebPages(currentFolderId);
}

// ── Bulk refresh ──
async function refreshAllStale() {
  const btn = document.querySelector('#staleAlert .btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Refreshing...'; }
  try {
    await api('/knowledge/urls/refresh-stale', { method: 'POST' });
    const poll = setInterval(async () => {
      try {
        const data = await api('/knowledge/urls/stale');
        if (data.stale_urls?.length === 0) {
          clearInterval(poll);
          loadWebPages(currentFolderId);
          return;
        }
      } catch (_) { /* retry on next tick */ }
    }, 2000);
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = 'Refresh all stale'; }
  }
}

// ── Delete ──
async function deleteWebPage(id) {
  showConfirm('Delete web page?', 'Chunks will be removed from the knowledge base.', async () => {
    await api(`/knowledge/urls/${id}`, { method: 'DELETE' });
    loadWebPages(currentFolderId);
  });
}

// ── Retry failed ──
async function retryWebPage(id) {
  await refreshWebPage(id);  // reuse refresh — same logic: re-fetch + re-index
}

// ── Stale alert ──
function updateStaleAlert(count) {
  const alert = document.getElementById('staleAlert');
  if (!alert) return;
  if (count > 0) {
    alert.style.display = 'flex';
    document.getElementById('staleCount').textContent = count;
  } else {
    alert.style.display = 'none';
  }
}

// ── Background stale poll (only while tab is active) ──
setInterval(async () => {
  if (activeTab === 'webpages') {
    try {
      const data = await api('/knowledge/urls/stale');
      updateStaleAlert(data.stale_urls?.length || 0);
    } catch (_) { /* silent */ }
  }
}, 30000);
```

### 4.5 Summary stats update (Documents tab)

Текущий summary включает URL:
```javascript
// Before: mixed files + URLs
summary.innerHTML = `... ${types['URL'] || 0} URLs ...`;

// After: only files
summary.innerHTML = `... ${fileCount} files, ${storageStr} used, ${chunkTotal} chunks`;
```

### 4.6 Documents list filter

Текущий `list_files` endpoint возвращает только `FileRecord.file_type == "document"` (line 421). Менять не нужно — URL уже отдельная модель и endpoint.

---

## 5. Optimization Opportunities (попутные улучшения)

| # | Оптимизация | Зачем | Сложность |
|---|------------|-------|-----------|
| 1 | **Import URL теперь inline, не modal** | Меньше кликов, выше discoverability | low |
| 2 | **Refresh all stale — batch endpoint** | Не надо обновлять по одному | low |
| 3 | **Stale alert с auto-dismiss** | Не мозолит глаза | low |
| 4 | **Background stale check (30s poll)** | Всегда актуальный статус | low |
| 5 | **Inline URL validation** | Ошибка видна до отправки формы | low |
| 6 | **URL truncation в таблице** | Длинные URL не ломают верстку | low |
| 7 | **Loading skeleton для URL table** | Лучше чем пустой экран | medium |
| 8 | **Import throttling** | Предотвращает двойной сабмит | low |

---

## 6. Files Changed

| File | Change | Lines +/- |
|------|--------|-----------|
| `api/app/templates/knowledge.html` | New tab panel, import bar, stale alert, URL table, JS functions | +200 / -30 |
| `api/app/knowledge/__init__.py` | New `PATCH /urls/{id}` + `POST /urls/refresh-stale` endpoints | +45 |

**No changes needed to:**
- Models (`models.py`) — `KnowledgeUrl` already exists
- API endpoints (existing) — `GET /knowledge/urls`, `POST /knowledge/urls`, etc.
- RAG pipeline — `rag.index_structured_text()` stays the same
- Folders — shared, no changes
- URL extraction (`url_extractor.py`) — no changes
- Main router (`main.py`) — no changes

---

## 7. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| **Folders break** — если folder_id ссылается на URL, который теперь в другом табе | low | medium | Folders shared; URL list endpoint уже фильтрует по folder_id |
| **Documents summary shows wrong counts** — если не убрать URL из подсчета | medium | low | Explicit count: только `FileRecord` для Documents таба |
| **Stale polling too aggressive** — 30s может быть много при 100+ URL | low | low | Увеличить до 60s, или только при активном табе |
| **Import URL no feedback** — user не видит что URL уже существует (duplicate check) | medium | medium | Показать в import result "Already imported" + ссылка на URL в таблице |
| **URL with no title** — если title не указан, показывать URL в колонке title | medium | low | Fallback: `title || url` |
| **Refresh all stale blocks** — последовательная обработка может быть медленной | low | medium | Запускать параллельно через `asyncio.gather()` с ограничением (5 concurrent) |
| **PATCH /urls/{id} endpoint не существует** — нужно создавать с нуля | high | medium | Уже добавлен в секцию 4.2. Структура запроса: `{url?: str, title?: str}` |
| **Double import без throttling** — пользователь может нажать Import дважды | medium | medium | `_importing` флаг + disable кнопки (уже в JS) |
| **Folder filter state сбрасывается при переключении табов** — выбранная папка в Documents не должна влиять на Web Pages | medium | low | Хранить `currentFolderId` отдельно для каждого таба |

---

## 8. Estimation

| Part | Hours |
|------|-------|
| Template: tab + panel structure | 1 |
| Template: import bar + stale alert | 1 |
| Template: URL table + all JS functions | 2-3 |
| Template: remove Import URL from Documents modal | 0.5 |
| Backend: `PATCH /urls/{id}` + `POST /urls/refresh-stale` | 1 |
| Testing: manual + edge cases | 1.5 |
| **Total** | **7-9** |
