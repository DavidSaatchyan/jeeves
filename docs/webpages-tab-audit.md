# Web Pages Tab — UX/UI Audit v2

**Дата:** 2026-06-09
**Файл:** `api/app/templates/knowledge.html` (1560 строк)
**Контекст:** Web Pages !== Documents. Это коллекция ссылок, а не файловая система. Не копируем Documents механически.

---

## 🐛 1. Критические баги (страница сломана)

### B1. Stale alert полностью не стилизован

**Строки:** 197–201
**Классы:** `.alert`, `.alert.warn`, `.alert-icon`
**Проблема:** CSS для этих классов **не определён** нигде в проекте. Баннер рендерится как голый `<div>` — без фона, бордера, паддинга. В тёмной теме просто невидим.

**Путь:** Добавить в `<style>` блок:
```css
.alert {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px; border-radius: var(--radius);
  font-size: 13px; margin-bottom: 16px;
}
.alert.warn {
  background: rgba(245, 166, 35, 0.08);
  border: 1px solid rgba(245, 166, 35, 0.2);
  color: var(--amber);
}
.alert-icon { font-size: 16px; flex-shrink: 0; }
#staleCount { font-weight: 700; color: var(--amber); }
```

---

### B2. Мёртвый JS-код (исправлено)

**Статус:** 🟢 Исправлено в `aeebb3e` — удалён дубликат `refreshFileRows()` с `return '<tr>'` вне функции.

---

## 🎨 2. Стилистические пробелы (элементы есть, но не стилизованы)

### C1. Нет CSS для `.col-title` и `.col-folder`

Колонки в шапке таблицы есть (L217–218), но CSS-ширина не задана — схлопываются по контенту.

**Решение:**
```css
.col-title { width: auto; min-width: 140px }
.col-folder { width: 130px }
```

### C2. Нет CSS для `.err-cell`

**Строка:** 1444 — `<td colspan="7" class="err-cell">` при ошибке загрузки.
Класс не определён — сообщение об ошибке без стиля.

**Решение:**
```css
.err-cell { padding: 24px; text-align: center; color: var(--red); font-size: 14px; }
```

### C3. Нет CSS для `.empty-state-icon`, `.empty-state-title`, `.empty-state-desc`

Классы используются (L230–234), но не определены в `knowledge.html` или `base.html`.

**Решение:**
```css
.empty-state-icon { font-size: 32px; margin-bottom: 12px; opacity: .4; }
.empty-state-title { font-size: 16px; font-weight: 700; margin-bottom: 8px; color: var(--text); }
.empty-state-desc { font-size: 13px; line-height: 1.6; color: var(--muted); max-width: 400px; margin: 0 auto; }
```

### C4. Нет CSS для `.kb-input.err`

`validateUrlInput()` добавляет класс `err`, но стиля нет — инпут не подсвечивается красным при невалидном URL.

**Решение:**
```css
.kb-input.err { border-color: var(--red); }
```

### C5. `kb-table-skeleton` structurally invalid

**Строки:** 204–209 — `<div class="kb-table-skeleton">` содержит `<table>`, но сам имеет `display: table-row-group`.

**Решение:** Убрать лишнюю вложенность:
```html
<tbody class="kb-table-skeleton" id="wpLoading" style="display:none">
  <tr class="skel-tr">...
</tbody>
```

### C6. Toolbar margin переопределён inline

**Строка:** 173 — `style="margin-bottom:12px"` вместо класса `16px` (L331).

**Решение:** Убрать inline-стиль.

---

## 🕹 3. UX-пробелы

### U1. Нет spinner при импорте URL

После нажатия "Import" нет обратной связи — пользователь не знает, выполняется ли операция.

**Решение:** В `importWebPage()`:
```js
document.getElementById('wpImportBtn').innerHTML = '<span class="kb-spinner"></span> Importing...';
```

### U2. Placeholder title не указывает на required

`placeholder="Page title"` — title обязателен (JS валидирует), но пользователь не знает.

**Решение:** `placeholder="Page title (required)"`

### U3. Нет авто-обновления статуса после импорта

URL висит "processing" до переключения таба. В Documents есть polling каждые 2s.

**Решение:** Добавить lightweight polling:
```js
var _idWpProcPoll = null;
function startWpProcPoll() {
  if (_idWpProcPoll) return;
  _idWpProcPoll = setInterval(function() {
    if (_activeTab === 'webpages') loadWebPages(_currentWpFolder);
  }, 3000);
}
function stopWpProcPoll() {
  if (_idWpProcPoll) { clearInterval(_idWpProcPoll); _idWpProcPoll = null; }
}
```

---

## 🔧 4. Исправления

### D1. Stale alert Dismiss скрывает навсегда

`onclick="this.parentElement.style.display='none'"` — только CSS-скрытие. При следующем `loadWebPages()` алерт появится снова, если URL всё ещё stale.

**Это OK** — алерт перерисовывается из `updateStaleAlert()` при каждой загрузке.

### D2. `retryWebPage()` — лишняя обёртка

Просто вызывает `refreshWebPage()`. Можно заменить в `renderActions()` прямой вызов.

### D3. Dismiss в stale alert без иконки/текста

Кнопка `×` — можно заменить на `Dismiss` для ясности (уже есть, OK).

---

## 5. Оптимизационные пути

### P0 — Срочно (30 мин)

| # | Задача | Время |
|---|--------|-------|
| 1 | CSS для `.alert`, `.alert.warn`, `.alert-icon`, `#staleCount` | 5 мин |
| 2 | CSS для `.col-title`, `.col-folder` | 3 мин |
| 3 | CSS для `.err-cell`, `.empty-state-*`, `.kb-input.err` | 5 мин |
| 4 | Исправить `.kb-table-skeleton` nesting | 3 мин |
| 5 | Убрать inline margin из wpToolbar | 2 мин |
| 6 | Spinner при импорте + placeholder "(required)" | 5 мин |
| 7 | Processing polling для URL (3s) | 10 мин |

### P1 — Следом (20 мин)

| # | Задача | Время |
|---|--------|-------|
| 8 | Добавить `<div class="card">`-обёртку вокруг таблицы с card-header | 10 мин |
| 9 | Clear all для URL | 10 мин |

### P2 — Не обязательно

- Sidebar tree вместо dropdown — **не нужно**, dropdown достаточно для коллекции ссылок
- Summary stats — **не нужно**, количество URL не релевантно (это не файлы)
- Folder management — **не нужно**, папки общие с Documents
- Card wrapper — **возможно**, смотри P1

---

## 6. Что НЕ надо менять (осознанные решения)

| Аспект | Решение | Почему |
|--------|---------|--------|
| Нет sidebar tree | Dropdown достаточен | Web Pages — коллекция ссылок, не файловая система |
| Нет summary stats | Просто таблица | Количество URL не метрика |
| Нет folder management | Из Documents | Папки общие, управление из Documents |
| Нет 6 skeleton rows | 3 строки | Загрузка быстрая (fetch, не файлы) |
| Нет 2-колоночного layout | Single column | Нет sidebar — нет 2 колонок |

---

## Сводка

```
P0: 7 задач  ─── 30 мин ─── 🐛 Всё сломанное
P1: 2 задачи ─── 20 мин ─── 🧹 Полировка
P2: 0 задач  ─── 0 мин  ─── ❌ Не нужно

Итого: 50 мин до продакшн-качества
```
