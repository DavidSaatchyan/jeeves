# Task Plan: Knowledge Base "Web Pages" Tab

**Разбивка на атомарные задачи.** Коммитить каждую задачу отдельно.

---

## Legend

| ID pattern | Meaning |
|-----------|---------|
| `BE-N` | Backend — новый endpoint |
| `FE-T-*` | Frontend — template HTML |
| `FE-JS-*` | Frontend — JavaScript |
| `FE-M-*` | Frontend — модификация существующего |
| `TST-*` | Tests |

---

## Phase 1: Backend — New API Endpoints

### BE-1: Pydantic schema `_UrlUpdateBody`

**File:** `api/app/knowledge/__init__.py`

```python
class _UrlUpdateBody(BaseModel):
    url: str | None = None
    title: str | None = None
```

**Acceptance:**
- `url` is optional (only update title if omitted)
- `title` is optional (only update URL if omitted)
- Both can be sent at once

**Time:** 5 min

---

### BE-2: `PATCH /knowledge/urls/{url_id}` endpoint

**File:** `api/app/knowledge/__init__.py`

```python
@router.patch("/urls/{url_id}")
def update_url(
    url_id: UUID,
    body: _UrlUpdateBody,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
```

**Logic:**
1. Fetch `KnowledgeUrl` by `url_id`
2. Verify tenant ownership
3. If `body.url` is not None and differs from current → update + set `changed = True`
4. If `body.title` is not None and differs from current → update (does NOT set `changed`)
5. If `changed` → trigger re-index via `asyncio.create_task(_background_index_url(tenant.id, url.id, url.url, url.title))`
6. Commit
7. Return `{"ok": True}`

**Dependencies:** BE-1

**Acceptance:**
- `PATCH /knowledge/urls/{id} {"title": "new"}` → updates title only, no re-index
- `PATCH /knowledge/urls/{id} {"url": "https://..."}` → updates URL + re-indexes
- `PATCH /knowledge/urls/{id} {}` → no-op, `{"ok": true}`
- 404 for unknown ID
- 404 for cross-tenant access

**Time:** 30 min

---

### BE-3: `POST /knowledge/urls/refresh-stale` endpoint

**File:** `api/app/knowledge/__init__.py`

```python
@router.post("/urls/refresh-stale")
def refresh_all_stale(
    max_age_hours: int = Query(72),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
```

**Logic:**
1. Query: `KnowledgeUrl WHERE tenant_id = X AND status = 'ready' AND last_fetched_at < now - 72h`
2. Set all to `status = 'processing'`
3. Commit
4. Fire `asyncio.create_task(_background_index_url(id))` for each (wrap in `asyncio.Semaphore(5)` to limit concurrent fetches)
5. Return `{"refreshed": N}`

**Acceptance:**
- `POST /knowledge/urls/refresh-stale` → returns `{"refreshed": 3}`
- All stale URLs have status `"processing"` in DB
- Background tasks are scheduled (verify via logs)

**Time:** 30 min

### BE-M1: Make `title` optional in existing `POST /knowledge/urls`

**File:** `api/app/knowledge/__init__.py`

**Changes:**
1. `_UrlImportIn.title: str` → `_UrlImportIn.title: str | None = None`
2. Remove `if not body.title.strip(): raise HTTPException(400, "title is required")`
3. On create, if `body.title` is None → set `title = body.url` (fallback)

**Why:** The new inline import bar in Web Pages tab treats title as optional. Backend must accept `{"url": "...", "folder_id": null}` without title.

**Acceptance:**
- `POST /knowledge/urls {"url": "https://..."}` → imports with auto-title (fallback to URL)
- `POST /knowledge/urls {"url": "https://...", "title": "Custom"}` → uses provided title

**Time:** 10 min

---

## Phase 2: Frontend — Template (knowledge.html)

### FE-T-1: Add "Web Pages" tab button

**Location:** `kb-tabs` div (between `documents` and `practice` `<a>` tags)

**Change:**
```html
<a class="kb-tab" data-tab="webpages" data-role="owner,manager" onclick="switchTab('webpages')">🌐 Web Pages</a>
```
Insert between `documents` and `practice` tab links.

**Note:** Must use `<a>` (not `<button>`) to match existing tab style. Must include `data-role` attribute for role-based visibility filtering.

**Acceptance:** Tab link visible in the tab bar, styled same as other tabs.

**Time:** 5 min

---

### FE-T-2: Add `#tab-webpages` tab panel

**Location:** After `<div id="tab-practice">` in the template.

**Structure:**
```html
<div id="tab-webpages" class="kb-tab-content" style="display:none">
  <!-- import bar -->
  <!-- stale alert -->
  <!-- loading -->
  <!-- table -->
  <!-- empty -->
</div>
```

**Note:** Must use class `kb-tab-content` (not `kb-panel`) to match existing tab convention (`tab-documents`, `tab-practice`). Must use `id="tab-webpages"` because `switchTab()` looks up `document.getElementById('tab-' + tab)`.

**CSS needed** (add to `<style>` block):
```css
.col-url{width:auto;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.col-url-val{cursor:pointer;color:var(--accent)}
.col-title-val{max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.col-fetched{width:115px;white-space:nowrap}
.kb-table th.col-url,.kb-table td.col-url{text-align:left}
```

**Acceptance:** Panel exists in DOM, hidden by default. Uses correct ID and class.

**Time:** 10 min

---

### FE-T-3: Import bar HTML

**Location:** Inside `#tab-webpages`

```html
<div id="webpages-import-bar" class="import-bar">
  <div class="import-bar-row">
    <input type="url" id="wpUrlInput" placeholder="https://example.com/clinic-policies"
           class="kb-input flex-2" oninput="validateUrlInput()" />
    <input type="text" id="wpTitleInput" placeholder="Page title (optional)" class="kb-input flex-1" />
    <select id="wpFolderSelect" class="kb-input">
      <option value="">No folder</option>
    </select>
    <button onclick="importWebPage()" class="btn accent" id="wpImportBtn">
      <span class="btn-icon">↗</span> Import
    </button>
  </div>
  <div id="wpImportResult" class="import-result" style="display:none"></div>
</div>
```

**Note:** Folder `<select>` will be populated by JS on tab switch (reuse existing folder list logic).

**Acceptance:** Import bar visible in Web Pages tab. Folder select present.

**Time:** 15 min

---

### FE-T-4: Stale alert HTML

**Location:** Inside `#tab-webpages`, above the table.

```html
<div id="staleAlert" class="alert warn" style="display:none">
  <span class="alert-icon">⚡</span>
  <span id="staleCount">0</span> web pages haven't been refreshed in over 72 hours.
  <button onclick="refreshAllStale()" class="btn sm accent">Refresh all stale</button>
  <button onclick="this.parentElement.style.display='none'" class="ghost sm">Dismiss</button>
</div>
```

**Acceptance:** Alert hidden by default. Shows with correct count when triggered.

**Time:** 10 min

---

### FE-T-5: URL table HTML

**Location:** Inside `#tab-webpages`, after stale alert.

```html
<div class="kb-table-wrap" style="overflow-x:auto">
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
    </tbody>
  </table>
</div>
```

**Acceptance:** Table visible. Empty body initially.

**Time:** 10 min

---

### FE-T-6: Loading skeleton HTML

**Location:** Inside `#tab-webpages`, above the table.

```html
<div class="kb-table-skeleton" id="wpLoading" style="display:none">
  <table class="kb-table"><tbody>
    <tr class="skel-tr"><td><div class="skel-line w80 skeleton"></div></td><td><div class="skel-line w60 skeleton"></div></td><td><div class="skel-line w40 skeleton" style="margin:0 auto"></div></td><td><div class="skel-line w50 skeleton" style="margin:0 auto"></div></td><td><div class="skel-line w30 skeleton" style="margin-left:auto"></div></td><td><div class="skel-line w40 skeleton"></div></td><td><div style="width:20px;height:20px"></div></td></tr>
    <tr class="skel-tr"><td><div class="skel-line w70 skeleton"></div></td><td><div class="skel-line w50 skeleton"></div></td><td><div class="skel-line w40 skeleton" style="margin:0 auto"></div></td><td><div class="skel-line w50 skeleton" style="margin:0 auto"></div></td><td><div class="skel-line w30 skeleton" style="margin-left:auto"></div></td><td><div class="skel-line w35 skeleton"></div></td><td><div style="width:20px;height:20px"></div></td></tr>
    <tr class="skel-tr"><td><div class="skel-line w85 skeleton"></div></td><td><div class="skel-line w65 skeleton"></div></td><td><div class="skel-line w40 skeleton" style="margin:0 auto"></div></td><td><div class="skel-line w50 skeleton" style="margin:0 auto"></div></td><td><div class="skel-line w30 skeleton" style="margin-left:auto"></div></td><td><div class="skel-line w50 skeleton"></div></td><td><div style="width:20px;height:20px"></div></td></tr>
  </tbody></table>
</div>
```

**Note:** Uses existing `skel-tr`/`skel-line`/`skeleton` classes (same as Documents tab) instead of `skel-card` (which exists only in `integrations_hub.html`).

**Acceptance:** Skeleton hidden by default. Shows during API call, matching Documents skeleton style.

**Time:** 5 min

---

### FE-T-7: Empty state HTML

**Location:** Inside `#tab-webpages`, after table.

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

**Acceptance:** Empty state hidden by default. Shows when URL list is empty and not loading.

**Time:** 5 min

---

### FE-T-8: Remove "Import URL" from Documents upload modal

**Location:** `#uploadModal` — exact lines to remove from `knowledge.html`:

**Template removals:**
1. Line 180: `<button class="ch-tab" data-utab="url">Import URL</button>` — remove tab button from `.ch-tabs` div
2. Lines 195-205: Remove entire `<div class="ch-panel" id="upanel-url">` block (URL input, title input, import button, status, error)

**JS removals:**
3. Lines 1156-1167: Remove `async function importUrl()` entirely
4. Remove `toggleImportBtn()` function reference (search for it — if it exists only for URL tab, remove it)
5. Remove `urlInput`, `urlTitle`, `importUrlBtn`, `urlStatus`, `urlErr` references from `showUploadModal()` (lines 1109-1114)

**Acceptance:** Upload modal in Documents tab only shows file upload (drag-drop / browse). No URL tab button, no URL form elements.

**Time:** 10 min

### FE-T-9: Folder filter dropdown in Web Pages table header

**Location:** Inside `#tab-webpages`, above the URL table, after stale alert.

**HTML:**
```html
<div class="kb-toolbar" id="wpToolbar" style="margin-bottom:12px">
  <span class="kb-current-folder" id="wpCurrentFolder">All URLs</span>
  <div class="kb-toolbar-actions">
    <select id="wpFolderFilter" class="kb-input" style="width:200px" onchange="loadWebPages(this.value)">
      <option value="">All folders</option>
    </select>
  </div>
</div>
```

**Note:** Folder `<select>` is populated by JS on tab switch (reuses folder list from `loadFolders()` but populates a `<select>`, not the sidebar tree). Must be isolated from Documents folder filter — changing folder in Documents must NOT affect Web Pages filter.

**Acceptance:** Folder dropdown visible in Web Pages tab. Selecting a folder filters the URL table. Default is "All folders".

**Time:** 10 min

### FE-T-10: Add CSS for new columns and states

**Location:** `<style>` block in `knowledge.html`

**Add:**
```css
.col-url{width:auto;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.col-url-val{color:var(--accent);cursor:pointer}
.col-title-val{max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.col-fetched{width:115px;white-space:nowrap}
.kb-table th.col-url,.kb-table td.col-url{text-align:left}
.import-bar{display:flex;flex-direction:column;gap:8px;margin-bottom:16px;padding:14px;background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:var(--radius)}
.import-bar-row{display:flex;gap:8px;align-items:center}
.import-bar-row .flex-1{flex:1}.import-bar-row .flex-2{flex:2}
.import-result{font-size:13px;padding:6px 0}
.import-result.ok{color:var(--green)}
.import-result.err{color:var(--red)}
```

**Time:** 5 min

---

## Phase 3: Frontend — JavaScript

### FE-JS-0: `showResult()` helper

```javascript
function showResult(elId, msg, type) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = msg;
  el.className = 'import-result ' + (type || '');
  el.style.display = msg ? 'block' : 'none';
}
```

**Note:** This function does NOT exist in `knowledge.html`. Must be added. Used by `importWebPage()` to show success/error messages inline.

**Time:** 3 min

---

### FE-JS-1: Constants + URL validation

```javascript
const URL_RE = /^https?:\/\/.+/i;

function validateUrlInput() {
  const el = document.getElementById('wpUrlInput');
  const val = el.value.trim();
  el.className = 'kb-input flex-2' + (val && !URL_RE.test(val) ? ' err' : '');
}
```

**Acceptance:** Input turns red when value doesn't start with http/https.

**Time:** 5 min

---

### FE-JS-2: Table loading state

```javascript
function showTableLoading(show) {
  document.getElementById('wpLoading').style.display = show ? 'block' : 'none';
  document.getElementById('wpBody').style.display = show ? 'none' : '';
  document.getElementById('wpEmpty').style.display = 'none';
}
```

**Acceptance:** Loading skeleton shows, table and empty state hide.

**Time:** 5 min

---

### FE-JS-3: `loadWebPages(folderId)` — fetch + render

```javascript
let _wpFolderMap = {};  // id → name mapping

async function loadWebPages(folderId) {
  showTableLoading(true);
  try {
    const [data, staleData, folders] = await Promise.all([
      api('/knowledge/urls' + (folderId ? `?folder_id=${folderId}` : '')),
      api('/knowledge/urls/stale'),
      api('/knowledge/folders'),
    ]);
    // Build folder name map for resolving folder_id → folder_name
    _wpFolderMap = {};
    function walk(fs) {
      fs.forEach(f => { _wpFolderMap[f.id] = f.name; if (f.children) walk(f.children); });
    }
    walk(folders.folders || []);
    renderTable(data.urls || []);
    updateStaleAlert(staleData.stale_urls?.length || 0);
  } catch (e) {
    document.getElementById('wpBody').innerHTML =
      `<tr><td colspan="7" class="err-cell">Error: ${e.message}</td></tr>`;
  } finally {
    showTableLoading(false);
  }
}
```

**Acceptance:** Table populates with rows. Stale alert updates. Folder names resolve correctly.

**Time:** 20 min

---

### FE-JS-4: `renderTable(urls)` — render table rows

```javascript
function _folderName(folderId) {
  return folderId ? _wpFolderMap[folderId] || '—' : '—';
}

function renderTable(urls) {
  const body = document.getElementById('wpBody');
  if (!urls.length) {
    document.getElementById('wpEmpty').style.display = 'block';
    body.innerHTML = '';
    return;
  }
  document.getElementById('wpEmpty').style.display = 'none';
  body.innerHTML = urls.map(u => {
    const isStale = u.status === 'ready' && isOlderThan(u.last_fetched_at, 72);
    const status = isStale ? 'stale' : u.status;
    const errorTitle = status === 'failed' && u.error ? ` title="${esc(u.error)}"` : '';
    return `<tr data-url-id="${u.id}">
      <td class="col-url-val" title="${esc(u.url)}" onclick="openChunkViewer('${u.id}', true, '${esc(u.title || u.url)}')">${truncateUrl(u.url)}</td>
      <td class="col-title-val">${esc(u.title || u.url)}</td>
      <td>${_folderName(u.folder_id)}</td>
      <td><span class="pill ${STATUS_PILLS[status] || 'muted'}"${errorTitle}>${status}</span></td>
      <td>${u.chunks_total ?? '—'}</td>
      <td>${u.last_fetched_at ? timeAgo(u.last_fetched_at) : '—'}</td>
      <td class="col-actions">${renderActions(status, u.id, u.title || u.url)}</td>
    </tr>`;
  }).join('');
}
```

**Supporting helpers:**
```javascript
const STATUS_PILLS = { ready: 'ok', stale: 'warn', processing: '', pending: 'muted', failed: 'err' };

function isOlderThan(dateStr, hours) {
  if (!dateStr) return true;
  return Date.now() - new Date(dateStr).getTime() > hours * 3600000;
}

function truncateUrl(url, max = 50) {
  return url.length > max ? url.slice(0, max) + '…' : url;
}

function timeAgo(date) {
  const diff = Date.now() - new Date(date).getTime();
  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff/60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff/3600000)}h ago`;
  return `${Math.floor(diff/86400000)}d ago`;
}

function renderActions(status, id, name) {
  const actions = [];
  if (status === 'ready' || status === 'stale') {
    actions.push(`<button onclick="openChunkViewer('${id}', true, '${esc(name)}')" class="btn xs ghost" title="View chunks">⊕</button>`);
    actions.push(`<button onclick="refreshWebPage('${id}')" class="btn xs ghost" title="Refresh">↻</button>`);
  }
  if (status === 'failed') actions.push(`<button onclick="retryWebPage('${id}')" class="btn xs ghost" title="Retry">↻</button>`);
  actions.push(`<button onclick="editWebPage('${id}')" class="btn xs ghost" title="Edit">✎</button>`);
  if (status !== 'processing') actions.push(`<button onclick="deleteWebPage('${id}')" class="btn xs ghost danger" title="Delete">✕</button>`);
  return actions.join(' ');
}
```

**Note on `_folderName()`:** The API returns `folder_id` (UUID), not `folder_name`. Client resolves name via `_wpFolderMap` built in `loadWebPages()` from the folders API. `_folderName()` is a module-level helper, not per-row.

**Note on error tooltip:** Failed URLs show error message as `title` attribute on the pill span (hover to see). Only applies when `status === 'failed'`.

**Note on `openChunkViewer`:** This function already exists in `knowledge.html` at line 1172. It opens a modal with chunks for both files and URLs (`isUrl=true` flag). URL column is also clickable to open chunk viewer.

**Acceptance:** Rows rendered with correct status pill, error tooltip for failed, "View chunks" ⊕ button for ready/stale, actions per status, truncated URL, time ago. URL column clickable → chunk viewer.

**Time:** 30 min

---

### FE-JS-5: `importWebPage()` — import with throttling

```javascript
let _importing = false;

async function importWebPage() {
  if (_importing) return;
  const url = document.getElementById('wpUrlInput').value.trim();
  const title = document.getElementById('wpTitleInput').value.trim();
  const folderId = document.getElementById('wpFolderSelect').value;
  if (!url) return showResult('wpImportResult', 'URL is required', 'err');
  if (!URL_RE.test(url)) return showResult('wpImportResult', 'URL must start with http:// or https://', 'err');
  if (!title) return showResult('wpImportResult', 'Title is required', 'err');
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
    loadWebPages(_currentWpFolder);
  } catch (e) {
    showResult('wpImportResult', e.message, 'err');
  } finally {
    _importing = false;
    document.getElementById('wpImportBtn').disabled = false;
  }
}
```

**Acceptance:** URL and title both required. Cannot double-submit. Success resets form. Error shown inline. Folder select empty string `""` → coerced to `null` by `folderId || null`.

**Time:** 15 min

---

### FE-JS-6: `editWebPage(id)` + `saveEdit(id)` — inline edit

```javascript
function editWebPage(id) {
  const row = document.querySelector(`tr[data-url-id="${id}"]`);
  const urlCell = row.querySelector('.col-url-val');
  const titleCell = row.querySelector('.col-title-val');
  urlCell.innerHTML = `<input type="url" class="kb-input" value="${esc(urlCell.textContent)}" id="edit-url-${id}" />`;
  titleCell.innerHTML = `<input type="text" class="kb-input" value="${esc(titleCell.textContent)}" id="edit-title-${id}" />`;
  row.querySelector('.col-actions').innerHTML =
    `<button onclick="saveEdit('${id}')" class="btn sm accent">Save</button>
     <button onclick="loadWebPages(_currentWpFolder)" class="btn sm ghost">Cancel</button>`;
}

async function saveEdit(id) {
  const newUrl = document.getElementById(`edit-url-${id}`).value.trim();
  const newTitle = document.getElementById(`edit-title-${id}`).value.trim();
  if (!newUrl || !URL_RE.test(newUrl)) return;
  await api(`/knowledge/urls/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ url: newUrl, title: newTitle }),
  });
  loadWebPages(_currentWpFolder);
}
```

**Acceptance:** Click Edit → URL and title become inputs. Save → PATCH call. Cancel → reload.

**Time:** 20 min

---

### FE-JS-7: `refreshWebPage(id)` — single refresh

```javascript
async function refreshWebPage(id) {
  await api(`/knowledge/urls/${id}/refresh`, { method: 'POST' });
  loadWebPages(_currentWpFolder);
}
```

**Acceptance:** Click refresh → status changes to processing → eventually back to ready.

**Time:** 5 min

---

### FE-JS-8: `refreshAllStale()` — batch refresh

```javascript
async function refreshAllStale() {
  const btn = document.querySelector('#staleAlert .btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="kb-spinner"></span> Refreshing...'; }
  try {
    await api('/knowledge/urls/refresh-stale', { method: 'POST' });
    await pollStaleCompletion();
  } catch (e) {
    if (btn) { btn.disabled = false; btn.innerHTML = 'Refresh all stale'; }
  }
}

function pollStaleCompletion() {
  return new Promise((resolve) => {
    const poll = setInterval(async () => {
      try {
        const data = await api('/knowledge/urls/stale');
        if (data.stale_urls?.length === 0) {
          clearInterval(poll);
          loadWebPages(_currentWpFolder);
          resolve();
        }
      } catch (_) { /* retry */ }
    }, 2000);
  });
}
```

**Note on spinner:** Uses existing `.kb-spinner` CSS class (defined at line 327 in `knowledge.html`). Button replaces text with spinner + "Refreshing..." during batch operation.

**Acceptance:** Button disabled + spinner + "Refreshing..." text. Polls until stale count is 0. Table reloads.

**Time:** 15 min

---

### FE-JS-9: `deleteWebPage(id)` — delete with confirm

```javascript
async function deleteWebPage(id) {
  showConfirm('Chunks will be removed from the knowledge base.', async () => {
    await api(`/knowledge/urls/${id}`, { method: 'DELETE' });
    loadWebPages(_currentWpFolder);
  }, 'Delete web page?');
}
```

**⚠️ CRITICAL: `showConfirm` signature is `(msg, cb, title?)`.** The message is the 1st arg, callback is 2nd, title is 3rd optional. This matches the existing function at line 1294 in `knowledge.html`. Do NOT swap the arguments.

**Acceptance:** Confirm modal appears with title "Delete web page?" and message "Chunks will be removed…". Confirm → delete + reload. Cancel → no-op.

**Time:** 5 min

---

### FE-JS-10: `retryWebPage(id)` — retry failed

```javascript
async function retryWebPage(id) {
  await api(`/knowledge/urls/${id}/refresh`, { method: 'POST' });
  loadWebPages(_currentWpFolder);
}
```

**Note:** Reuses the refresh endpoint — same logic: re-fetch + re-index.

**Acceptance:** Click Retry on failed URL → status → processing → ready/failed.

**Time:** 5 min

---

### FE-JS-11: `updateStaleAlert(count)` + background polling

```javascript
function updateStaleAlert(count) {
  const alert = document.getElementById('staleAlert');
  if (!alert) return;
  alert.style.display = count > 0 ? 'flex' : 'none';
  document.getElementById('staleCount').textContent = count;
}

// Background poll — only while tab is active
var _idWpPoll = null;

function startWpPoll() {
  if (_idWpPoll) return;
  _idWpPoll = setInterval(async () => {
    if (_activeTab === 'webpages') {
      try {
        const data = await api('/knowledge/urls/stale');
        updateStaleAlert(data.stale_urls?.length || 0);
      } catch (_) { /* silent */ }
    }
  }, 30000);
}

function stopWpPoll() {
  if (_idWpPoll) {
    clearInterval(_idWpPoll);
    _idWpPoll = null;
  }
}
```

**Note on `_idWpPoll`:** Must be declared as `var` alongside existing `_idDocPoll` and `_idPmsPoll` (line 442-443 in `knowledge.html`). Must be stopped in `switchTab()` when leaving webpages tab (see FE-JS-12).

**Note on `_activeTab`:** Uses existing module-level variable (line 440). NOT `activeTab`.

**Acceptance:** Stale alert appears/disappears based on API response. Polling starts when Web Pages tab activates, stops when leaving tab. No interval leak.

---

### FE-JS-12: Update `switchTab()` for 3 tabs + hash whitelist

**Location:** Existing `switchTab()` function in `knowledge.html` (lines 468-494)

**A) Add `'webpages'` to hash whitelist** (lines 448-449):

```javascript
// Before:
if(['documents','practice'].indexOf(hash) >= 0) {

// After:
if(['documents','webpages','practice'].indexOf(hash) >= 0) {
```

**B) Add `'webpages'` to hashchange listener** (lines 454-456):

```javascript
// Before:
if(['documents','practice'].indexOf(hash) >= 0) {

// After:
if(['documents','webpages','practice'].indexOf(hash) >= 0) {
```

**C) Add `_currentWpFolder` state variable** (near line 441):
```javascript
var _currentWpFolder = null;  // Web Pages tab folder filter (isolated from Documents)
```

**D) Update `switchTab()` body** — add webpages handling:
```javascript
function switchTab(tab, pushState) {
  if(pushState !== false) {
    history.replaceState(null, '', '#' + tab);
  }
  if(_activeTab === 'documents' && tab !== 'documents') _savedFolder = _selectedFolder;
  closeAllModals();
  if(_idDocPoll) { clearInterval(_idDocPoll); _idDocPoll = null; }
  if(_idPmsPoll) { clearInterval(_idPmsPoll); _idPmsPoll = null; }
  stopWpPoll();
  _activeTab = tab;
  document.querySelectorAll('.kb-tab-content').forEach(function(el){ el.style.display = 'none'; });
  document.getElementById('tab-' + tab).style.display = '';
  document.querySelectorAll('.kb-tab').forEach(function(el){ el.classList.remove('active'); });
  var tabEl = document.querySelector('.kb-tab[data-tab="' + tab + '"]');
  if(tabEl) tabEl.classList.add('active');
  try {
    if(tab === 'documents') {
      if(_savedFolder) { _selectedFolder = _savedFolder; selectFolder(_savedFolder); }
      loadFolders();
      refresh();
      _idDocPoll = setInterval(refreshFileRows, 2000);
    }
    if(tab === 'webpages') {
      loadWpFolderSelect();  // populate import bar + filter dropdowns
      loadWebPages(_currentWpFolder);
      startWpPoll();
    }
    if(tab === 'practice') {
      loadPmsStatus().then(function(){ loadHmsTable(); });
      _idPmsPoll = setInterval(loadPmsStatus, 30000);
    }
  } catch(e) { console.error('switchTab error:', e); }
}
```

**E) Add `loadWpFolderSelect()` function** (populates `#wpFolderSelect` and `#wpFolderFilter`):
```javascript
async function loadWpFolderSelect() {
  try {
    const data = await api('/knowledge/folders');
    const folders = data.folders || [];
    const opts = [['', 'No folder']];
    function walk(fs, depth) {
      fs.forEach(f => {
        opts.push([f.id, '  '.repeat(depth) + f.name]);
        if (f.children) walk(f.children, depth + 1);
      });
    }
    walk(folders, 0);
    // Populate import bar folder dropdown
    const sel = document.getElementById('wpFolderSelect');
    sel.innerHTML = opts.map(([v, label]) => `<option value="${v}">${label}</option>`).join('');
    // Populate table filter dropdown
    const filter = document.getElementById('wpFolderFilter');
    filter.innerHTML = '<option value="">All folders</option>' +
      opts.slice(1).map(([v, label]) => `<option value="${v}"${v === _currentWpFolder ? ' selected' : ''}>${label}</option>`).join('');
  } catch(e) { console.error('loadWpFolderSelect error:', e); }
}
```

**F) Update folder filter `onchange`** to update `_currentWpFolder`:
```javascript
// In FE-T-9 HTML, onchange handler should be:
// onchange="_currentWpFolder=this.value; loadWebPages(this.value)"
```

**Acceptance:** Hash whitelist includes 'webpages'. `_idWpPoll` is cleaned up on tab switch. `_currentWpFolder` is isolated from Documents `_selectedFolder`. Switching to Web Pages tab populates folder dropdowns and triggers data load. Switching back to Documents preserves folder filter.

**Time:** 20 min

---

### FE-JS-13: Update Documents summary stats

**Location:** Existing summary stats rendering in Documents tab.

**Change:** Remove URL count from the summary:
```javascript
// Before:
summary.innerHTML = `... ${types['URL'] || 0} URLs ...`;
// After:
// URLs are no longer counted in Documents summary
```

**Acceptance:** Documents summary shows only files, storage, chunks (no URL count).

**Time:** 5 min

---

## Phase 4: Tests

### TST-1: BE — PATCH /knowledge/urls/{id}

**File:** `api/tests/test_knowledge_urls.py`

**Test cases:**
1. Update title only → returns `{"ok": true}`, title changed in DB, URL unchanged
2. Update URL only → returns `{"ok": true}`, triggers re-index
3. Update both → both changed
4. Empty body → no-op
5. 404 for non-existent ID
6. 404 for cross-tenant ID

**Time:** 30 min

---

### TST-2: BE — POST /knowledge/urls/refresh-stale

**Test cases:**
1. No stale URLs → `{"refreshed": 0}`
2. 3 stale URLs → `{"refreshed": 3}`, all marked "processing"
3. Recently fetched URLs are NOT included
4. Failed URLs are NOT included (only `status == 'ready'`)

**Time:** 20 min

---

### TST-3: FE — Manual smoke test checklist

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| 1 | Tab switch | Click "Web Pages" tab | Panel shows, loading skeleton → table |
| 2 | Empty state | Open Web Pages with no URLs | Empty state shows |
| 3 | Import URL | Enter valid URL → Import | Row appears with "processing" → "ready" |
| 4 | Import invalid URL | Enter "blah" → Import | Error "URL must start with http:// or https://" |
| 5 | Import duplicate | Import same URL twice | Error "Already imported" |
| 6 | Edit title | Click Edit → change title → Save | Title updates immediately |
| 7 | Edit URL | Click Edit → change URL → Save | URL updates + re-indexes |
| 8 | Refresh single | Click Refresh on ready URL | Status → processing → ready |
| 9 | Stale detection | Mock `last_fetched_at` > 72h | Stale alert shows |
| 10 | Refresh all stale | Click "Refresh all stale" | All stale URLs refresh |
| 11 | Delete | Click Delete → confirm | Row removed |
| 12 | Retry failed | Mock failed status → Click Retry | Re-fetches |
| 13 | Documents unaffected | Switch to Documents | No URL count in summary, no Import URL in modal |
| 14 | Folder filter | Select folder in Web Pages | Only URLs in that folder shown |
| 15 | Background poll | Wait 30s (mock) | Stale alert updates without page reload |

**Time:** 1h

---

## Dependency Graph

```
BE-M1 (title optional) ◀─── required by FE-JS-5
BE-1 (schema) ──▶ BE-2 (PATCH endpoint)
               └─▶ BE-3 (refresh-stale + Semaphore)

FE-T-1 (tab button) ──▶ FE-T-2 (tab-webpages panel)
                            │
               ┌────────────┼────────────┼────────────┐
               ▼            ▼            ▼            ▼
          FE-T-3       FE-T-4       FE-T-5       FE-T-9
        (import bar) (stale alert)  (table)   (folder filter)
               │            │            │            │
               ▼            ▼            ▼            │
          FE-T-6 (loading) ─── FE-T-7 (empty)         │
                                    │                 │
                                    ▼                 ▼
                              FE-T-8 (remove URL)  FE-T-10 (CSS)

All FE-T ──▶ FE-JS-0 (showResult) ──▶ FE-JS-1 (validation)
                                      FE-JS-2 (loading)
                                      FE-JS-3 (loadWebPages + folder map)
                                      FE-JS-4 (renderTable + error tooltip + view chunks)
                                      FE-JS-5 (importWebPage)
                                      FE-JS-6 (editWebPage)
                                      FE-JS-7 (refreshWebPage)
                                      FE-JS-8 (refreshAllStale + spinner)
                                      FE-JS-9 (deleteWebPage)
                                      FE-JS-10 (retryWebPage)
                                      FE-JS-11 (updateStaleAlert + _idWpPoll)
                                      FE-JS-12 (switchTab + hash + _currentWpFolder)
                                      FE-JS-13 (Documents summary)

All FE-JS ──▶ TST-1, TST-2, TST-3
```

---

## Summary

| Layer | Tasks | Hours |
|-------|-------|-------|
| Backend | BE-1, BE-2, BE-3, BE-M1 | 1.25 |
| Template | FE-T-1..10 | 1.25 |
| JavaScript | FE-JS-0..13 | 3 |
| Tests | TST-1, TST-2, TST-3 | 2 |
| **Total** | **28 tasks** | **~7.5** |
