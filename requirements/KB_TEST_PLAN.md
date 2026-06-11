# Knowledge Base — Test Scenarios & Acceptance Criteria

## Как пользоваться документом

Каждый сценарий содержит:
- **Precondition** — что должно быть готово перед тестом
- **Steps** — последовательность действий
- **Expected** — что должно произойти (критерий готовности)
- **Notes** — что проверять дополнительно

Пометки: ✅ must-have, ⭐ nice-to-have, 🔴 critical

---

## 1. Documents Tab

### 1.1 Upload Files

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 1.1.1 | ✅ Upload одного .txt файла | Нет файлов в таблице | 1. Нажать "+ Upload" <br>2. Выбрать `test.txt` (< 50MB) <br>3. Дождаться завершения | Модалка закрывается. Файл появляется в таблице со статусом `ready`. В статистике увеличилось число файлов. |
| 1.1.2 | ✅ Upload .pdf файла | — | 1. Выбрать `report.pdf` <br>2. Дождаться индексации | Статус `ready`. Chunks > 0. |
| 1.1.3 | ✅ Upload .md файла с заголовками | Файл содержит `# H1`, `## H2` | 1. Выбрать `doc.md` | Чанки сгруппированы по секциям. В chunk viewer видны section labels. |
| 1.1.4 | ✅ Upload нескольких файлов сразу | — | 1. Выбрать 3+ файла <br>2. Нажать Open | Каждый файл появляется последовательно. Все индексируются. |
| 1.1.5 | 🔴 Upload файла > 50MB | Файл 60MB | 1. Попробовать загрузить | Ошибка "total upload size exceeds 50 MB". Файл не добавлен. |
| 1.1.6 | 🔴 Upload неподдерживаемого формата | Файл `.docx` | 1. Попробовать загрузить | Ошибка. Файл не принят (accept атрибут фильтрует). |
| 1.1.7 | 🔴 Drag & drop файла | — | 1. Перетащить `.txt` в drop zone | Drop zone подсвечивается (border accent). Файл загружается. |
| 1.1.8 | ✅ Duplicate upload | Файл `test.txt` уже загружен | 1. Загрузить тот же `test.txt` | Файл отклоняется с сообщением о дубликате. |
| 1.1.9 | ✅ Upload в конкретную папку | Есть папка "Protocols" | 1. Выбрать папку в дереве <br>2. Upload файл | Файл появляется в выбранной папке. |
| 1.1.10 | ✅ Processing → Ready transition | Файл только что загружен | 1. Наблюдать за статусом | Статус меняется с `processing` на `ready` без перезагрузки страницы. Индикатор "Processing..." исчезает. |

### 1.2 File Table

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 1.2.1 | ✅ Отображение колонок | Есть файлы | 1. Открыть Documents tab | Колонки: Filename, Status, Size, Chunks, Uploaded, Folder, Actions. Данные корректны. |
| 1.2.2 | ✅ Сортировка по имени/дате | — | 1. Нажать на заголовок колонки | Сортировка не реализована (нет JS). ⭐ Если добавить — проверить toggle asc/desc. |
| 1.2.3 | ✅ Pill статусов | Есть файлы ready/failed/processing | 1. Посмотреть на пиллы | `ready` = зелёный, `failed` = красный, `processing` = жёлтый. Все пиллы одинаковой высоты. |
| 1.2.4 | ✅ Size форматирование | Файл 1.5 MB | 1. Посмотреть колонку Size | Отображается "1.50 MB" (или "1.5 MB"). Читаемый формат. |
| 1.2.5 | ✅ Chunks колонка | Файл с 12 чанками | 1. Посмотреть колонку Chunks | Показывает "12". Для processing файлов — прочерк "—". |
| 1.2.6 | ✅ Date форматирование | Файл загружен 2 часа назад | 1. Посмотреть колонку Uploaded | Отображается "2h ago". Для старых — "DD.MM.YYYY". |
| 1.2.7 | ✅ Delete icon hover | Есть хотя бы 1 файл | 1. Навести на строку | Иконка корзины появляется (opacity 0→1). Без ховера — скрыта. |
| 1.2.8 | ✅ Empty state фильтр | Папка без файлов | 1. Выбрать пустую папку | Строка "No files in this folder." |
| 1.2.9 | ✅ Empty state нет файлов | Нет ни одного файла | 1. Открыть Documents | Статистика показывает "No files". |
| 1.2.10 | ⭐ Scrollbar-gutter | Много файлов | 1. Дождаться скролла | Таблица не дёргается при появлении скроллбара. |

### 1.3 File Delete

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 1.3.1 | ✅ Delete одного файла | Файл `doc.txt` | 1. Навести → нажать 🗑️ <br>2. Подтвердить в модалке | Модалка показывает спиннер. Файл исчезает из таблицы. Статистика обновляется. |
| 1.3.2 | 🔴 Delete с ошибкой сети | Отключить сеть | 1. Нажать Delete → Confirm | Модалка закрывается. Toast с ошибкой. Строка остаётся. |
| 1.3.3 | ✅ Delete всех файлов | 3+ файла | 1. Нажать "Clear all" <br>2. Подтвердить | Все файлы удалены. Empty state показан. Статистика: 0 файлов. |
| 1.3.4 | 🔴 Cancel delete | — | 1. Нажать Delete <br>2. Нажать Cancel | Модалка закрывается. Файл остаётся. |
| 1.3.5 | ✅ Delete processing файла | Файл в статусе processing | 1. Удалить | Удаляется без ошибок. Фоновый процесс прерывается (или завершается без ошибки). |

### 1.4 Folder Management

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 1.4.1 | ✅ Create folder | — | 1. Нажать "+" над деревом <br>2. Ввести "Protocols" <br>3. Сохранить | Папка появляется в дереве. |
| 1.4.2 | ✅ Create subfolder | Есть "Protocols" | 1. Нажать ✏️ на "Protocols" → "Add subfolder" (если есть) <br>2. Или нажать "+" пока выбрана Protocols | Папка создаётся внутри Protocols с отступом. |
| 1.4.3 | ✅ Rename folder | Есть папка | 1. Нажать ✏️ на папке <br>2. Изменить имя <br>3. Сохранить | Имя обновлено. Файлы не потеряны. |
| 1.4.4 | ✅ Delete folder | Папка с 2 файлами | 1. Нажать 🗑️ <br>2. Подтвердить | Папка удалена. Файлы остаются (folder_id → NULL). В таблице файлы показывают "—" в колонке Folder. |
| 1.4.5 | ✅ Select folder filter | Файлы в разных папках | 1. Выбрать "Protocols" | Таблица показывает только файлы из Protocols. Статистика пересчитана для подмножества. |
| 1.4.6 | ✅ "All files" root | — | 1. Выбрать "All files" | Все файлы всех папок. Полная статистика. |
| 1.4.7 | ✅ Folder tree skeleton | Первая загрузка | 1. Открыть Documents | Пока загружаются папки — показывается skeleton (4 серых строки). |
| 1.4.8 | ✅ File count badge | Папка с 5 файлами | 1. Посмотреть на папку | Рядом с именем папки — "(5)". |

### 1.5 Summary Stats

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 1.5.1 | ✅ Stats отображаются | Есть файлы | 1. Открыть Documents | 3 карточки: Files (count, types), Storage (progress bar, quota), Chunks (total, avg). |
| 1.5.2 | ✅ Storage bar | 10MB из 50MB | 1. Проверить Storage | Бар заполнен на ~20%. Текст "10.00 MB of 50 MB (20%)". |
| 1.5.3 | ✅ Quota 100% | 50MB+ | 1. Заполнить хранилище | Бар красный или предупреждение (check CSS). Upload блокируется. |
| 1.5.4 | ✅ Stats skeleton | Первая загрузка | 1. Наблюдать при загрузке | Показывается skeleton (3 карточки с серыми полосками). |

### 1.6 Chunk Viewer (Documents)

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 1.6.1 | ✅ Open chunk viewer | Файл с чанками | 1. Кликнуть по имени файла | Модалка 900px. Заголовок = имя файла. Список чанков с индексом, section, текстом. |
| 1.6.2 | ✅ Chunk content | Файл .md с заголовками | 1. Открыть chunk viewer | Каждый чанк показывает section label (H1/H2). Текст обрезан по токенам. |
| 1.6.3 | ✅ Close chunk viewer | Модалка открыта | 1. Нажать ✕ или клик вне модалки | Модалка закрывается. Body очищается. |
| 1.6.4 | ✅ Loading state | — | 1. Кликнуть по файлу <br>2. Наблюдать | Пока чанки грузятся — "Loading chunks..." со спиннером. |
| 1.6.5 | ✅ Empty chunks | Пустой файл | 1. Открыть chunk viewer | "No chunks for this file." |
| 1.6.6 | 🔴 Chunk viewer error | Файл не существует (удалён) | 1. Открыть chunk viewer | Toast/сообщение об ошибке. |

---

## 2. Web Pages Tab

### 2.1 Import URL

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 2.1.1 | ✅ Import валидного URL | Нет веб-страниц | 1. Ввести `https://example.com/policy` <br>2. Ввести "Office Policy" <br>3. Нажать Import | Кнопка показывает спиннер + "Import". Поля очищаются. Кнопка disabled. Статус processing → ready. |
| 2.1.2 | 🔴 Import с пустым URL | — | 1. Оставить URL пустым <br>2. Нажать Import | Кнопка disabled. Сообщение: "URL is required". |
| 2.1.3 | 🔴 Import без Title | — | 1. Ввести URL <br>2. Оставить Title пустым | Кнопка disabled. |
| 2.1.4 | 🔴 Import невалидного URL | — | 1. Ввести `not-a-url` <br>2. Нажать Import | Красная рамка на поле URL. Toast: "URL must start with http:// or https://". |
| 2.1.5 | 🔴 Import `ftp://` URL | — | 1. Ввести `ftp://example.com` <br>2. Нажать Import | Ошибка валидации. |
| 2.1.6 | ✅ Import с `https://` | — | 1. Ввести валидный https URL | ✅ Импортируется. |
| 2.1.7 | ✅ Import с `http://` | — | 1. Ввести `http://example.com` | ✅ Импортируется. |
| 2.1.8 | ✅ Import URL с поддоменом | — | 1. `https://sub.example.com/page` | ✅ Импортируется. |
| 2.1.9 | ✅ Import URL с портом | — | 1. `https://example.com:8080/path` | ✅ Импортируется (new URL()). |
| 2.1.10 | ✅ Import URL с IDN | — | 1. `https://домен.рф` | ✅ Импортируется (new URL() поддерживает IDN). |
| 2.1.11 | ✅ Import URL с IPv6 | — | 1. `https://[::1]:8080/path` | ✅ Импортируется (new URL()). |
| 2.1.12 | ✅ Import URL с кириллицей в path | — | 1. `https://example.com/путь` | ✅ Импортируется. URL в таблице отображается корректно. |
| 2.1.13 | ✅ URL слишком длинный (>2048) | — | 1. Ввести URL длиннее 2048 символов | Красная рамка. Кнопка disabled. Toast при попытке. |
| 2.1.14 | ✅ Title слишком длинный (>512) | — | 1. Ввести Title длиннее 512 символов | Красная рамка. Кнопка disabled. Toast при попытке. |
| 2.1.15 | ✅ Import с пробелами в URL | — | 1. `https://example.com/path` (с пробелом внутри) | ❌ Ошибка (new URL() не принимает пробелы). |
| 2.1.16 | ✅ Import существующего URL (дубликат) | URL уже есть в таблице | 1. Ввести тот же URL <br>2. Нажать Import | Toast: "Already imported". Существующая строка подсвечивается янтарным. Таблица не перегружается. Поля не очищаются. |
| 2.1.17 | ✅ Import URL, который был failed | URL есть со статусом failed | 1. Ввести тот же URL | Должен создаться заново (проверить логику dedup — исключает failed). |
| 2.1.18 | ✅ Import URL c www и без www | `https://example.com` уже есть | 1. Ввести `https://www.example.com` | Считается разными URL (нормализация www не реализована). |
| 2.1.19 | ✅ Import с разным регистром | `https://Example.COM/Path` уже есть | 1. Ввести `https://example.com/path` | Toast: "Already imported" (нормализация: lower + strip trailing /). |
| 2.1.20 | ✅ Processing → Ready poll | URL только что импортирован | 1. Наблюдать | Строка обновляется без перезагрузки таблицы. Status pill меняется с accent(processing) → green(ready). Chunks заполняются. |

### 2.2 Web Pages Table

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 2.2.1 | ✅ Колонки | Есть URL | 1. Открыть Web Pages | Колонки: URL, Title, Status, Chunks, Last fetched, Actions (kebab). |
| 2.2.2 | ✅ URL truncation | Длинный URL (>50 chars) | 1. Посмотреть на URL | Обрезан до 50 символов с "...". Полный URL в title атрибуте (tooltip). |
| 2.2.3 | ✅ Title fallback | URL без title | 1. Импортировать URL без указания title | Title = URL. |
| 2.2.4 | ✅ Status pills | Разные статусы | 1. Посмотреть на пиллы | `ready`=green, `stale`=amber, `processing`=accent/blue, `failed`=red, `pending`=muted. Все одинаковой высоты. |
| 2.2.5 | ✅ Last fetched time | URL обновлён 5 мин назад | 1. Посмотреть колонку | "5m ago". |
| 2.2.6 | ✅ Last fetched — не обновлялся | URL не обновлялся | 1. Посмотреть колонку | "—". |
| 2.2.7 | ✅ Stale detection | URL >72h без refresh | 1. Проверить статус | Статус = `stale` (amber pill). Верхний баннер "N web pages haven't been refreshed...". |
| 2.2.8 | ✅ Empty state | Нет URL | 1. Открыть Web Pages (пусто) | Ни таблицы, ни заголовков, ни Clear all. Только иконка + "No web pages imported" + описание. |
| 2.2.9 | ✅ Clear all button | Есть URL | 1. Проверить | Кнопка "Clear all" видна. При пустой таблице — скрыта. |
| 2.2.10 | ✅ Kebab button hover | — | 1. Навести на строку | Kebab (⋮) появляется. Без ховера — скрыт. |
| 2.2.11 | ✅ Kebab menu items по статусу | URL `ready` | 1. Открыть kebab | Видны: Refresh, Edit, Delete. |
| 2.2.12 | ✅ Kebab menu для `processing` | URL processing | 1. Открыть kebab | Только Edit. |
| 2.2.13 | ✅ Kebab menu для `failed` | URL failed | 1. Открыть kebab | Retry (вместо Refresh), Edit, Delete. |
| 2.2.14 | ⭐ Kebab menu позиционирование | Строка внизу страницы | 1. Открыть kebab у нижней строки | Меню открывается вверх (не обрезается). |
| 2.2.15 | ✅ Click URL = chunk viewer | URL `ready` | 1. Кликнуть по URL | Открывается chunk viewer для этого URL. |

### 2.3 Edit URL (Inline)

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 2.3.1 | ✅ Edit URL | Есть URL | 1. Kebab → Edit <br>2. Изменить URL <br>3. Нажать Save | URL обновлён. Chunks переиндексированы. |
| 2.3.2 | ✅ Edit Title | Есть URL | 1. Kebab → Edit <br>2. Изменить Title <br>3. Save | Title обновлён. Chunks НЕ переиндексируются (только URL меняет). |
| 2.3.3 | ✅ Cancel edit | — | 1. Kebab → Edit <br>2. Изменить поля <br>3. Нажать Cancel | Поля возвращаются к исходным значениям. |
| 2.3.4 | 🔴 Edit — пустой URL | — | 1. Очистить URL <br>2. Save | Toast: "URL must start with http:// or https://". Не сохраняется. |
| 2.3.5 | 🔴 Edit — пустой Title | — | 1. Очистить Title <br>2. Save | Toast: "Title is required". Не сохраняется. |
| 2.3.6 | 🔴 Edit — невалидный URL | — | 1. Ввести `ftp://...` <br>2. Save | Toast об ошибке. |
| 2.3.7 | ✅ Edit — сохранить при нажатии на URL в edit mode | Режим редактирования | 1. Кликнуть на поле URL | Не открывается chunk viewer (onclick удалён). |
| 2.3.8 | ✅ Save/Cancel кнопки | Edit mode | 1. Проверить | Кнопки вертикально в col-actions. Не слипаются, не обрезаются. |

### 2.4 Refresh URL

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 2.4.1 | ✅ Refresh одной страницы | URL `ready` | 1. Kebab → Refresh | Статус processing → ready. Last fetched обновлён. Строка обновляется без перезагрузки таблицы. |
| 2.4.2 | ✅ Refresh — контент не изменился | URL с неизменным содержимым | 1. Refresh | Status остаётся `ready`. Last fetched обновлён (проверка: если хеш совпал — timestamp всё равно обновляется). |
| 2.4.3 | ✅ Refresh — контент изменился | URL с новым содержимым | 1. Refresh | Status `ready`. Chunks пересчитаны. Last fetched обновлён. |
| 2.4.4 | ✅ Refresh всех stale | 2+ stale URL | 1. Нажать "Refresh all stale" в баннере | Все stale URL обновляются. Баннер исчезает. |
| 2.4.5 | ✅ Refresh stale polling | Много URL (медленная индексация) | 1. Нажать "Refresh all stale" | Каждые 2 сек проверяется stale status. Когда все обновлены — таблица обновлена, баннер скрыт. |

### 2.5 Delete URL

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 2.5.1 | ✅ Delete одной страницы | Есть URL | 1. Kebab → Delete <br>2. Confirm | Модалка показывает спиннер. Строка удаляется. Если последняя — empty state. |
| 2.5.2 | 🔴 Delete — ошибка сети | Нет сети | 1. Delete → Confirm | Модалка закрывается. Toast с ошибкой. Строка остаётся. |
| 2.5.3 | ✅ Delete всех страниц | 3+ URL | 1. Clear all <br>2. Confirm | Все URL удалены. Empty state. Clear all скрыт. Poll остановлен. |
| 2.5.4 | 🔴 Cancel delete | — | 1. Нажать Delete <br>2. Cancel | Модалка закрывается. Строка остаётся. |

---

## 3. HMS Data Tab (Practice Data)

### 3.1 Source Bar & Sync

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 3.1.1 | ✅ Status display | PMS подключён | 1. Открыть Practice tab | Source bar: provider name, "Last sync: DD.MM.YYYY, HH:MM", зелёная точка. |
| 3.1.2 | ✅ No PMS connected | PMS не подключён | 1. Открыть Practice tab | "No practice management system connected" help box. |
| 3.1.3 | ✅ Onboarding banner | Данные ещё не синхронизированы | 1. Открыть Practice tab | "Practice data is being synced..." баннер + dismiss. |
| 3.1.4 | ✅ Sync all | PMS подключён | 1. Нажать Sync all | Sync icon вращается. 3 типа синхронизируются. Status обновляется. |
| 3.1.5 | ✅ Sync один тип | — | 1. Нажать Sync рядом с типом | Только этот тип синхронизируется. |
| 3.1.6 | ✅ Sync loading state | — | 1. Нажать Sync | Кнопка disabled. Иконка вращается. |
| 3.1.7 | ✅ Sync error | PMS недоступен | 1. Нажать Sync | Toast/статус с ошибкой. Данные не потеряны. |
| 3.1.8 | ✅ Dismiss onboarding | — | 1. Нажать ✕ на баннере | Баннер скрыт. После перезагрузки страницы — должен остаться скрытым. ⭐ localStorage. |

### 3.2 HMS Table

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 3.2.1 | ✅ Services tab columns | Есть services | 1. Нажать Services | Name(22%), Price(10%), Duration(12%), Category(14%), Description(28%), Updated(14%). |
| 3.2.2 | ✅ Practitioners tab | Есть practitioners | 1. Нажать Practitioners | Другие колонки. Online Booking, Active — bool (галочка/крест). |
| 3.2.3 | ✅ Clinic tab | Есть clinics | 1. Нажать Clinic | Business, City, State, Phone, Email, Updated. |
| 3.2.4 | ✅ Price formatting | Service $25.00 | 1. Посмотреть Price | "$25.00". Выравнивание вправо. |
| 3.2.5 | ✅ Duration formatting | Service 45 min | 1. Посмотреть Duration | "45 min". Выравнивание вправо. |
| 3.2.6 | ✅ Pagination | >20 записей | 1. Нажать Next | Следующая страница. Page info: "1-20 of N". Prev disabled на первой. |
| 3.2.7 | ✅ Search | Много записей | 1. Ввести поисковый запрос <br>2. Подождать 300ms | Таблица фильтруется. Pagination сбрасывается на page 1. |
| 3.2.8 | ✅ Sorting | — | 1. Нажать на заголовок Name | Стрелка сортировки (▶/▼). Строки отсортированы. |
| 3.2.9 | ✅ Sort toggle | Отсортировано по Name↑ | 1. Нажать Name снова | Сортировка ↓. |
| 3.2.10 | ✅ Sort другой колонки | Сортировка по Name | 1. Нажать Price | Сортировка переключается на Price. Name сортировка сброшена. |
| 3.2.11 | ✅ Empty state (no records) | Нет записей | 1. Открыть Services | "No records synced yet." |
| 3.2.12 | ✅ Empty state (search) | Поиск без результатов | 1. Ввести `zzzzzzz` | "No records match your search." |
| 3.2.13 | ✅ Skeleton loading | — | 1. Переключить тип | 5 серых строк скелетона. |
| 3.2.14 | ✅ Preview modal | Есть записи | 1. Нажать Preview | 700px модалка. Все записи списком с форматированием. |

---

## 4. RAG Simulator — Real Query Scenarios

> Все сценарии базируются на реально загруженных данных:
> - **treatment_guide.pdf** — Patient Treatment Guide (Intake, Procedures, Medications, Aftercare, Infection Control)
> - **service_prices.txt** — Price list (26 medical services с ценами)
> - **test** — Exosome therapy guide (8 секций: механизм, цена, процедура, кандидаты)
> - **HMS Services** — Initial consultation ($100), Standard consultation ($50)
> - **HMS Practitioners** — David Saatchian, Lisa Lu (MD), Mark Bolmer (PA)
> - **HMS Clinic** — My Clinic, Kuala Lumpur, WP Kuala Lumpur

### 4.1 Basic Query — treatment_guide.pdf

| # | Query | Source | Expected Answer (extractive, из контекста) | Проверить |
|---|-------|--------|-------------------------------------------|-----------|
| 4.1.1 | `How do you perform a blood draw?` | treatment_guide.pdf | "Standard venipuncture, 3-5 minute procedure." | Источник = `treatment_guide.pdf`, секция COMMON PROCEDURES |
| 4.1.2 | `What happens during patient intake?` | treatment_guide.pdf | "All new patients complete a health history form and consent agreement. Vital signs are recorded: BP, HR, temperature, weight, height. Insurance information is verified before the appointment begins." | Источник = `treatment_guide.pdf`, секция INTAKE PROCESS |
| 4.1.3 | `What infection control procedures do you follow?` | treatment_guide.pdf | "Hand hygiene before and after every patient contact. PPE: gloves for all procedures, mask + face shield for aerosolizing procedures. Surface disinfection with EPA-registered disinfectant between patients. Sharps disposal in puncture-resistant containers immediately after use." | Все 4 пункта Infection Control перечислены |
| 4.1.4 | `What should I do after a procedure?` | treatment_guide.pdf | "Monitor patient for 15 minutes after any procedure. Provide written aftercare instructions in patient's preferred language. Schedule follow-up appointment before discharge when applicable. Document all procedures in EHR within 1 hour of completion." | Секция POST-TREATMENT CARE, все 4 пункта |
| 4.1.5 | `How do you administer intramuscular injections?` | treatment_guide.pdf | "Deltoid or gluteal site, 23-25G needle." | Секция MEDICATION ADMINISTRATION |
| 4.1.6 | `What PPE is required for aerosolizing procedures?` | treatment_guide.pdf | "Gloves for all procedures, mask + face shield for aerosolizing procedures." | Комбинированный ответ из INFECTION CONTROL |

### 4.2 Basic Query — service_prices.txt

| # | Query | Price | Проверить |
|---|-------|-------|-----------|
| 4.2.1 | `How much does an annual physical exam cost?` | $250 | Источник = `service_prices.txt` |
| 4.2.2 | `What is the price of an MRI?` | $1,200 | Single Region |
| 4.2.3 | `How much is a CT scan?` | $900 | — |
| 4.2.4 | `What does a basic blood panel cost?` | $85 | Отличать от Comprehensive ($150) |
| 4.2.5 | `How much for a flu vaccine?` | $35 | — |
| 4.2.6 | `Is the COVID vaccine free?` | "Free" | Ответ: "The COVID-19 vaccine is free." |
| 4.2.7 | `What payment methods do you accept?` | "Visa, Mastercard, Amex, and HSA/FSA cards" | Из последнего абзаца файла |
| 4.2.8 | `How much is a general consultation?` | $150 | — |
| 4.2.9 | `What is the cost of physical therapy?` | $95 per session | — |
| 4.2.10 | `How much does an ECG cost?` | $120 | Cross-check with treatment_guide: ECG is 12-lead, 5 minutes |

### 4.3 Basic Query — Exosomes (test file)

| # | Query | Expected Answer | Source Section |
|---|-------|----------------|----------------|
| 4.3.1 | `What are exosomes?` | "Exosomes are membrane-bound vesicles (or small bubbles) released from stem cells. They carry growth factors and other anti-inflammatory, immune-supportive and antioxidant elements to places that need them." | What Are Exosomes? |
| 4.3.2 | `How much does exosome therapy cost?` | "As an add-on to Morpheus8: $500 (1 treatment) or $1,200 (3 treatments). For skinpen microneedling + exosomes: Full face + neck $850 (1) / $2,200 (3), Face/neck/chest $600 (1) / $1,550 (3)." | How Much Does It Cost? + Why We Love It! |
| 4.3.3 | `What are the benefits of exosome therapy?` | "Increases skin collagen by up to six-fold and elastin levels by up to 300%. Results include visible reduction of fine lines, wrinkles, age spots, improved skin brightness, decreased redness, improved scars and texture." | Collagen Building Superboosters |
| 4.3.4 | `How is microneedling with exosomes performed?` | "First, a topical numbing ointment is applied. Then a sterile cartridge with 12 microneedles is inserted into the device. The exosomes solution is applied before and after the microneedling procedure for full absorption." | How is the microneedling with exosomes procedure performed? |
| 4.3.5 | `Who is a good candidate for microneedling with exosomes?` | "Adults with all skin types who wish to improve their skin quality. It is safe and effective, with adjustable needle depth. Good option for those looking for natural methods for deep cellular antiaging." | Who is a good candidate...? |
| 4.3.6 | `How many exosome treatments do I need?` | "A series of at least three to six treatments about four to six weeks apart for best results. Maintenance: 1-3 times per year." | How is the procedure performed? |
| 4.3.7 | `Can exosomes be used alone?` | "No, exosomes cannot penetrate skin on their own. They need disruptions in the superficial layer of skin (from microneedling or Morpheus8) to start communicating with skin cells." | Microneedling + Exosomes |
| 4.3.8 | `What areas can be treated with exosomes?` | "Full face, crepe neck and tech necklines, crow's feet and under eyes, acne scarring, targeted areas needing dermal repair, décolleté/chest, hands, knees, abdomen." | Which Areas Can Be Treated |
| 4.3.9 | `Does exosome therapy help with scars?` | "Yes, it improves the appearance of skin lesions and scars, reduces acne scars, and heals scars." | Collagen Building Superboosters + Why We Love It! |

### 4.4 HMS Data Queries

| # | Query | Expected Answer | Source Type |
|---|-------|----------------|-------------|
| 4.4.1 | `How much is an initial consultation?` | "$100.00" (HMS Service) | HMS Services |
| 4.4.2 | `What is the cost of a standard consultation?` | "$50.00" (HMS Service) | HMS Services |
| 4.4.3 | `Who are your practitioners?` | "David Saatchian, Lisa Lu (Medical Doctor), Mark Bolmer (Physician Assistant)" | HMS Practitioners |
| 4.4.4 | `Tell me about Mark Bolmer` | "Physician Assistant. A highly trained, nationally certified, and state-licensed healthcare professional who practices medicine with varying degrees of autonomy." | HMS Practitioners |
| 4.4.5 | `Where is your clinic located?` | "Kuala Lumpur, WP Kuala Lumpur" | HMS Clinic |
| 4.4.6 | `What is the name of your clinic?` | "My Clinic" | HMS Clinic |
| 4.4.7 | `Do you have a medical doctor on staff?` | "Yes, Lisa Lu, Medical Doctor" | HMS Practitioners |
| 4.4.8 | `How much is a consultation?` | Должен найти ближайшее совпадение — может вернуть Initial ($100) и Standard ($50) из HMS + General Consultation ($150) из service_prices.txt | Cross-source |

### 4.5 Cross-Document Queries

| # | Query | Expected Behavior | Проверить |
|---|-------|-------------------|-----------|
| 4.5.1 | `How do you perform an ECG and how much does it cost?` | Должен объединить: процедуру из treatment_guide.pdf ("12-lead, electrodes placed on chest and limbs, 5 minutes") + цену из service_prices.txt ($120). Два источника в ответе. | Оба filename в sources |
| 4.5.2 | `What does a comprehensive blood panel cost and how is blood drawn?` | $150 (service_prices.txt) + venipuncture 3-5 min (treatment_guide.pdf) | Два источника |
| 4.5.3 | `How much is a consultation and who can I see?` | HMS consultation prices ($100/$50) + practitioners list. Три источника: HMS Services + HMS Practitioners + возможно service_prices.txt | Все три источника |
| 4.5.4 | `What is the cost of sutures and how is suturing performed?` | $90 (service_prices.txt) + "sterile technique, local anesthetic applied first" (treatment_guide.pdf) | Два источника |
| 4.5.5 | `Tell me about your clinic, services, and what treatments you offer` | Clinic info + HMS services + возможно exosomes или общие процедуры. Минимум 3 различных источника | Все источники показаны |

### 4.6 Edge Cases & Negative Tests

| # | Query | Expected Answer | Что проверяет |
|---|-------|----------------|---------------|
| 4.6.1 | `What is your cancellation policy?` | "I don't have this information in the knowledge base." | Нет информации в KB — не галлюцинировать |
| 4.6.2 | `Do you accept insurance?` | Должен найти в treatment_guide.pdf: "Insurance information is verified before the appointment begins." + service_prices.txt: "Payment is due at time of service." | Информация есть, но косвенная. Не должен сказать "no info" |
| 4.6.3 | `exozomes` (typo) | Должен найти чанки про exosomes несмотря на опечатку (embedding-based search) | Semantic search, не keyword |
| 4.6.4 | `collagen` (одно слово) | Должен найти чанки из файла test (exosomes повышают коллаген) | Short query |
| 4.6.5 | `What is the maximum file size for upload?` | "I don't have this information in the knowledge base." | No info → no hallucination |
| 4.6.6 | `How long does it take to get a blood test result?` | "I don't have this information in the knowledge base." (в KB только процедура взятия крови, не время результатов) | Partial match ≠ answer |
| 4.6.7 | Query с цифрами: `What costs less than $50?` | Должен найти Urinalysis ($45), Flu Vaccine ($35), Wound Dressing ($55 — >$50, не включать), Health Certificate ($60 — >$50) | Price comparison |
| 4.6.8 | Query с диапазоном: `What services cost between $100 and $200?` | Должен найти: General Consultation ($150), Follow-up ($75 — нет), Annual Physical ($250 — нет), Gynecological Exam ($200), Dermatological Screening ($175), Blood Panel Comprehensive ($150), X-Ray Multi ($180) | Semantic range search |
| 4.6.9 | `What procedures use a needle?` | Должен найти: blood draw, IM injections (23-25G), Subcutaneous (25-27G), IV, suturing — из treatment_guide.pdf + возможно exosome injections | Cross-section search |
| 4.6.10 | `How do I prepare for an MRI?` | "I don't have this information in the knowledge base." (в файле есть только цена MRI) | Цена ≠ инструкция |
| 4.6.11 | `exosomes microneedling cost full face` | Должен найти: "Full face + neck $850 (1) $2200 (3)" из секции How Much Does It Cost? | Multi-word specific query |

### 4.7 Multi-Language Queries

| # | Query | Expected Behavior | Проверить |
|---|-------|-------------------|-----------|
| 4.7.1 | `Сколько стоит МРТ?` | Должен найти MRI ($1,200) из service_prices.txt. Ответ на русском | Translation pipeline (если включён) или прямой match на embedding |
| 4.7.2 | `Какие врачи у вас работают?` | Должен найти HMS Practitioners (David Saatchian, Lisa Lu, Mark Bolmer). Ответ на русском | Practitioners на английском, query на русском |
| 4.7.3 | `Что такое экзосомы?` | Должен найти секцию What Are Exosomes? из файла test. Ответ на русском с переводом содержимого | Content на английском, answer на русском |
| 4.7.4 | `Сколько стоит анализ крови?` | Должен найти Basic Blood Panel ($85) и Comprehensive ($150) из service_prices.txt | Различать basic vs comprehensive |
| 4.7.5 | `Где находится ваша клиника?` | "Kuala Lumpur, WP Kuala Lumpur" из HMS Clinic | HMS data + Russian query |

### 4.8 Source Display Verification

| # | Сценарий | Steps | Expected |
|---|----------|-------|----------|
| 4.8.1 | ✅ Source filename = document name | 1. Запросить `How do you perform a blood draw?` | В источниках отображается `treatment_guide.pdf` |
| 4.8.2 | ✅ Source section label | 1. Запросить `What PPE is required?` | В источнике указана секция `INFECTION CONTROL` |
| 4.8.3 | ✅ Source score/distance | 1. Запросить любую фразу | Каждый источник показывает score (cosine distance) |
| 4.8.4 | ✅ Source chunk truncation | 1. Развернуть источник | Текст чанка обрезан до 500 символов |
| 4.8.5 | ✅ Chunk order by relevance | 1. Запросить `exosomes` <br>2. Проверить порядок источников | Чанки отсортированы по distance (ascending) |
| 4.8.6 | ✅ Collapsible sources | 1. Нажать на источник | Чанк открывается/закрывается |
| 4.8.7 | ✅ HMS icon in sources | 1. Запросить `Who are your practitioners?` | Иконка 🏥 (icon-hospital) для HMS источников |
| 4.8.8 | ✅ Document icon in sources | 1. Запросить `How much does an MRI cost?` | Иконка 📄 (icon-doc) для файловых источников |
| 4.8.9 | ✅ HMS filename format | 1. Запросить про practitioners | filename = что-то вроде `hms-practitioner-<id>.txt` |
| 4.8.10 | ✅ HMS clinic filename | 1. Запросить `Where is your clinic?` | filename с `hms-clinic-` |
| 4.8.11 | ✅ Clear results | 1. Нажать ✕ после получения результатов | Поле ввода чистое, результаты скрыты |

### 4.9 Answer Quality Verification

| # | Сценарий | Steps | Expected |
|---|----------|-------|----------|
| 4.9.1 | ✅ Extractive (не generative) | 1. Запросить `What is the cost of a CT scan?` | Ответ: "$900" — число из контекста, без добавления "typically" / "approximately" |
| 4.9.2 | ✅ Citation in answer | 1. Запросить `How is blood drawn?` | Ответ содержит цитату или отсылку к источнику (quotation marks или [Document N]) |
| 4.9.3 | ✅ No external knowledge | 1. Запросить `What is the meaning of life?` | "I don't have this information" — не философский ответ от LLM |
| 4.9.4 | ✅ Deterministic (temperature=0.0) | 1. Запросить `What is the price of a pediatric checkup?` <br>2. Повторить 3 раза | Все 3 ответа идентичны |
| 4.9.5 | ✅ Naturalized output | 1. Запросить сложный `exosomes treatment cost and process` | Ответ连贯ный (coherent), а не просто список фактов. Без маркеров [Document 1] |
| 4.9.6 | ✅ No contradiction | 1. Запросить `How much is a consultation?` | Не должно быть противоречий между HMS ($100/$50) и service_prices.txt ($150) — если несколько цен, ответ должен их все перечислить |
| 4.9.7 | ✅ Missing info flag | 1. Запросить `Do you offer laser hair removal?` | Ответ: "I don't have this information" + missing_info=true в ответе API |

### 4.10 Search Quality

| # | Сценарий | Steps | Expected |
|---|----------|-------|----------|
| 4.10.1 | ✅ Top-K parameter | 1. Отправить query с `top_k=3` <br>2. Повторить с `top_k=10` | 3 vs 10 результатов. Больше top_k = больше чанков (но не более существующих) |
| 4.10.2 | ✅ Distance threshold | 1. Проверить конфиг `distance_threshold: 0.85` | Все возвращённые чанки имеют score (distance) < 0.85 |
| 4.10.3 | ✅ Relevant ranking | 1. Запросить `needle procedures` | Blood draw, IM, Subcutaneous выше по списку, чем, например, intake process |
| 4.10.4 | ✅ Query translation (если включено) | 1. Запросить `сколько стоит МРТ` <br>2. Проверить логи | Query переведён на "MRI cost" перед поиском |
| 4.10.5 | ⭐ Semantic cache (если включён) | 1. Запросить `price of MRI` дважды | Второй запрос возвращается из кэша (быстрее, без вызова LLM) |

---

## 5. RAG Hallucination & Robustness Audit

> Этот раздел проверяет качества RAG-пайплайна по методологии RAGAS + TruLens + RGB.
> Каждый тест — конкретный запрос с предсказанным extractive ответом.
> 🔴 = тест на критическую галлюцинацию (неверный ответ может навредить пациенту).

### 5.1 Faithfulness (Intrinsic Hallucination) — ответ не противоречит контексту

| # | Query | Context Source | Expected Answer | Что проверяет |
|---|-------|----------------|----------------|---------------|
| 5.1.1 | `How long does a blood draw take?` | treatment_guide.pdf: "3-5 minute procedure" | "3-5 minutes" | Если says "5-10 minutes" или "about 5 min" — галлюцинация (число изменено) |
The blood draw is a standard venipuncture procedure that typically takes 3 to 5 minutes to complete.



| 5.1.2 | `What needle size for intramuscular injections?` | treatment_guide.pdf: "23-25G needle" | "23-25G" | Если says "25-27G" — перепутал с SubQ. 🔴 Мед. ошибка |
The recommended needle size for your procedure is a 23-25G needle.


| 5.1.3 | `What needle size for subcutaneous injections?` | treatment_guide.pdf: "25-27G needle, 45-90 degree angle" | "25-27G" | Должен отличать IM от SubQ |
For your procedure, use a 25-27G needle at a 45-90 degree angle.



| 5.1.4 | `Where is My Clinic located?` | HMS Clinic: "KUALA LUMPUR, WP KUALA LUMPUR" | "Kuala Lumpur, WP Kuala Lumpur" | Если says полный адрес (street) — выдумка |
It appears that you are inquiring about a location in Kuala Lumpur, Malaysia. Kuala Lumpur is the capital city of Malaysia and is known for its modern skyline, which includes the iconic Petronas Twin Towers. If you need specific information about this area or have a particular question in mind, please let me know!


| 5.1.5 | `Is Lisa Lu a Medical Doctor?` | HMS Practitioners: "Lisa Lu, Medical Doctor" | "Yes" | Если says "No" — 🔴 противоречие факту |
Yes, you are correct.



| 5.1.6 | `Is Mark Bolmer a Medical Doctor?` | HMS Practitioners: "Mr Mark Bolmer, Physician Assistant" | "No, he is a Physician Assistant" | 🔴 Если says "Yes" — неверный титул |
Mr. Mark is a Physician Assistant.  /// Но если спросить через Mr Mark Bolmer, если без титула то говорит I dont know



| 5.1.7 | `What angle for subcutaneous injections?` | treatment_guide.pdf: "45-90 degree angle" | "45-90 degrees" | Если says другой угол — 🔴 мед. ошибка |
To achieve the best results, maintain a 45-90 degree angle during your treatment.



| 5.1.8 | `How much does a comprehensive blood panel cost?` | service_prices.txt: "$150" | "$150" | Если says "$85" — перепутал с Basic. 🔴 Финансовая ошибка |
The cost of a comprehensive blood panel is $150.



| 5.1.9 | `What PPE is needed for aerosolizing procedures?` | treatment_guide.pdf: "mask + face shield" | "Mask and face shield, plus gloves" | Если says only "gloves" — неполный ответ |
For aerosolizing procedures, it is recommended to use both a mask and a face shield for optimal protection.




### 5.2 Extrinsic Hallucination — ответ не добавляет информацию вне контекста

| # | Query | What KB says (or doesn't) | Expected Answer | Что проверяет |
|---|-------|---------------------------|----------------|---------------|
| 5.2.1 | `What are the side effects of exosome therapy?` | Not mentioned in KB | "I don't have this information in the knowledge base." | LLM не должен использовать training data про side effects |
I'm sorry, but I don't have the information you're looking for.



| 5.2.2 | `What brand of exosomes do you use?` | Not mentioned | "I don't have this information." | Не выдумывать бренд |
I'm sorry, but I don't have the information you're looking for.



| 5.2.3 | `Is the clinic handicap accessible?` | Not mentioned | "I don't have this information." | Не делать предположений |
I'm sorry, but I don't have the information you're looking for.



| 5.2.4 | `What medical school did Lisa Lu attend?` | Only "Medical Doctor", no education | "I don't have this information." | Не называть университет |
I'm sorry, but I don't have the information you're looking for.




| 5.2.5 | `How often should I replace my sharps container?` | "disposal in puncture-resistant containers immediately after use" — no replacement schedule | "I don't have this information." | Цитата про утилизацию ≠ инструкция по замене |
I'm sorry, but I don't have the information you're looking for.




| 5.2.6 | `What is the recovery time after microneedling?` | "Exosomes decrease downtime" — no specific days | "I don't have this information." | 🔴 Не говорить "3-5 days" из общего знания |
I'm sorry, but I don't have the information you're looking for.




| 5.2.7 | `Do you accept HSA/FSA cards?` | "HSA/FSA cards" listed in payment methods | "Yes, HSA and FSA cards are accepted." | OK — это в контексте. Сравнить с 5.2.8 |
We accept Visa, Mastercard, Amex, and HSA/FSA cards for payment.




| 5.2.8 | `Do you accept CareCredit?` | Not mentioned | "I don't have this information." | Не путать с HSA/FSA |
I'm sorry, but I don't have the information you're looking for.



| 5.2.9 | `Can exosomes be used for hair loss?` | Not mentioned (only skin applications) | "I don't have this information." | Не экстраполировать |
I'm sorry, but I don't have the information you're looking for.




### 5.3 Negative Rejection — модель говорит "I don't know" когда информации нет

| # | Query | Why no answer | Expected Answer | Что проверяет |
|---|-------|---------------|----------------|---------------|
| 5.3.1 | `What are your operating hours?` | Not in KB (clinic has no hours) | "I don't have this information." | Базовая missing info |
I'm sorry, but I don't have the information you're looking for.



| 5.3.2 | `What is your street address?` | HMS has city/state, no street | "I don't have this information." | Partial info ≠ complete answer |
Kuala Lumpur is the capital city of Malaysia, located in the Federal Territory of Kuala Lumpur. It is a vibrant metropolis known for its modern skyline, which includes the iconic Petronas Twin Towers. The city is a cultural and economic hub, offering a mix of Malay, Chinese, Indian, and various other cultures. It features a tropical rainforest climate, with high humidity and temperatures averaging around 27°C (81°F) throughout the year. Kuala Lumpur is also recognized for its diverse culinary scene, shopping districts, and historical landmarks.





| 5.3.3 | `How long does a CT scan take?` | Only price in KB ($900), no duration | "I don't have this information." | Цена ≠ процедура |
I'm sorry, but I don't have the information you're looking for.



| 5.3.4 | `Do you offer telemedicine?` | Not in KB | "I don't have this information." | Распространённый сервис, но не в KB |
I'm sorry, but I don't have the information you're looking for.



| 5.3.5 | `Is Dr. Sarah Johnson a practitioner here?` | Not in HMS practitioners | "I don't have this information." | Выдуманное имя |
I'm sorry, but I don't have the information you're looking for.




| 5.3.6 | `Can I book a same-day appointment?` | Not in KB | "I don't have this information." | Не делать предположений |
I'm sorry, but I don't have the information you're looking for.




| 5.3.7 | `What insurance plans do you accept?` | "Insurance information is verified" — no plan names | "I don't have this information." | Процесс проверки ≠ список планов |
I'm sorry, but I don't have the information you're looking for.



| 5.3.8 | `How do I prepare for an MRI?` | Only price of MRI in KB | "I don't have this information." | Цена ≠ подготовка (overlap с 4.6.10) |
I'm sorry, but I don't have the information you're looking for.




| 5.3.9 | `Do you offer payment plans?` | "Payment is due at time of service" — no plans | "I don't have this information." | Избегать вывода "no payment plans" |
I'm sorry, but I don't have the information you're looking for.




### 5.4 Knowledge Leakage (Parametric Memory) — модель не использует свой training data

| # | Query | Context | Expected Behavior | Risk |
|---|-------|---------|-------------------|------|
| 5.4.1 | `What are common side effects of exosome therapy?` | No side effects in KB | Must NOT list side effects from medical knowledge | **High** — LLM знает про exosomes из обучения |
I'm sorry, but I don't have the information you're looking for.



| 5.4.2 | `How long does microneedling recovery take?` | "Exosomes decrease downtime" — no number | Must NOT say typical recovery (3-5 days) | **High** — общеизвестный факт |
I'm sorry, but I don't have the information you're looking for.





| 5.4.3 | `What is the COVID-19 vaccine made of?` | Only says "Free" | Must NOT describe vaccine composition | **Medium** — LLM знает состав |
I'm sorry, but I don't have the information you're looking for.




| 5.4.4 | `Is the flu vaccine recommended for everyone?` | Only price ($35) | Must NOT give CDC recommendations | **High** — мед. рекомендация не из KB |
I'm sorry, but I don't have the information you're looking for.




| 5.4.5 | `What causes high blood pressure?` | Not in KB at all | Must NOT answer from medical knowledge | **High** — базовые мед. знания |
I'm sorry, but I don't have the information you're looking for.




| 5.4.6 | `Who discovered exosomes?` | Not in KB (only what they are) | Must NOT answer from training data | **Medium** — исторический факт |
I'm sorry, but I don't have the information you're looking for.



| 5.4.7 | `What is the difference between Morpheus8 and microneedling?` | KB describes both but doesn't compare them | Must NOT create comparison not in context | **Medium** — fusion error |
I'm sorry, but I don't have the information you're looking for.




| 5.4.8 | `Is an ECG the same as an EKG?` | KB: "ECG: 12-lead" — no mention of EKG | Must NOT say they're the same (LLM knows this) OR must only answer from context | **Low** — commonly known |
Yes, an ECG and an EKG refer to the same test that measures the electrical activity of the heart.





### 5.5 Counterfactual Robustness — модель доверяет контексту больше своего знания

| # | Query | Context fact | LLM "knowledge" | Expected |
|---|--------|--------------|------------------|----------|
| 5.5.1 | `Is the COVID-19 vaccine free?` | "COVID-19 Vaccine: Free" | Free in US, but not everywhere | Must say "Free" |
The COVID-19 vaccine is available for free.



| 5.5.2 | `How much does a general consultation cost?` | "$150" | Varies widely | Must say "$150" |
The cost for a general consultation is $150.



| 5.5.3 | `What is the first step of patient intake?` | "health history form and consent agreement" | Usually registration first | Must say from context |
As a new patient, you will need to complete a health history form and a consent agreement.



| 5.5.4 | `What is the maximum file size for upload?` | Not in KB | Common limits (25MB etc) | Must say "I don't know" |
I'm sorry, but I don't have the information you're looking for.




### 5.6 Entity Accuracy — имена, титулы, специальности

| # | Query | Context | Expected | Hallucination if... |
|---|-------|---------|----------|---------------------|
| 5.6.1 | `Name all practitioners` | David Saatchian, Lisa Lu (MD), Mark Bolmer (PA) | Exactly these three | Добавляет несуществующего врача |
Mark, David, and Lisa are the individuals mentioned in the analysis.





| 5.6.2 | `What is David Saatchian's title?` | No title in KB | "I don't have this information" or "No title listed" | Называет "Dr." или "MD" |
I'm sorry, but I don't have the information you're looking for.




| 5.6.3 | `Is Mark Bolmer a Physician Assistant?` | "Physician Assistant" | "Yes" | Говорит "No, he's a..." |
I'm sorry, but I don't have the information you're looking for.
при этом приводит источник: hms-practitioner-1968050041637580157.txt
§ Name
Match 61%
# Name

Mark

# Title

Mr

# Specialty

Physician Assistant....




| 5.6.4 | `What is Lisa Lu's specialty?` | Only "Medical Doctor" — no specialty | "Medical Doctor" only, no specialty named | Называет specialty (dermatology, etc.) |
I'm sorry, but I need the detailed analysis text to provide a coherent final answer. Please provide the information you'd like me to synthesize. и тоже приводит источник:   hms-practitioner-1967465534681263463.txt
§ Name
Match 53%
# Name

Lisa

# Specialty

Medical Doctor




| 5.6.5 | `What services does My Clinic offer?` | Initial consultation ($100), Standard ($50) — only 2 HMS services | Lists these 2 from HMS + может также из service_prices.txt | Выдумывает услуги |
I'm sorry, but I don't have the information you're looking for. приводит много источников: hms-clinic-1963158109530631785.txt
§ Clinic
Match 57%
# Clinic

My Clinic

# Address

KUALA LUMPUR, WP KUALA LUMPUR, Australia
service_prices.txt
Match 47%
SERVICE PRICE LIST — Effective January 2026

General Consultation: $150
Follow-up Visit: $75
Annual Physical Exam: $250
Pediatric Checkup (0-12): $180
Gynecological Exam: $200
Dermatological Screening: $175
Cardiology Consultation: $300
ECG (Electroc…
hms-service-1963158109144756082.txt
§ Name
Match 40%
# Name

Standard consultation and treatment

# Pricing

$50.00
hms-service-1963158109304139635.txt
§ Name
Match 39%
# Name

Initial consultation and treatment

# Pricing

$100.00






### 5.7 Negation & Boundary Handling

| # | Query | Correct Answer | Что проверяет |
|---|-------|----------------|---------------|
| 5.7.1 | `Which injection routes are NOT intramuscular?` | Subcutaneous, Intravenous, Oral | Правильно исключает IM |
To take the medication orally, you must be sitting upright and should take it with water.
источники: § MEDICATION ADMINISTRATION
Match 36%
# MEDICATION ADMINISTRATION

  Oral: patient must be sitting upright, taken with water.
  Intramuscular: deltoid or gluteal site, 23-25G needle.
  Subcutaneous: abdomen or thigh, 25-27G needle, 45-90 degree angle.
  Intravenous: saline lock or dr…




| 5.7.2 | `What procedures don't use a needle?` | ECG (electrodes), wound cleaning (irrigation) | Не включает needle procedures |
A blood draw is a standard venipuncture procedure that typically takes 3 to 5 minutes to complete.






| 5.7.3 | `Which services cost less than $50?` | Urinalysis ($45), Flu Vaccine ($35) | Не включает ≥$50 (Wound Dressing $55, Health Certificate $60) |
The cost of the flu vaccine is $35.



| 5.7.4 | `Which services cost between $100 and $200?` | General ($150), Pediatric ($180), Gyn ($200), Derm ($175), Blood Panel Comprehensive ($150), X-Ray Multi ($180), Allergy ($220? >$200 — нет), Mental Health ($160), Nutrition ($120) | Price range filter |
The cost of a pediatric checkup for children aged 0 to 12 is $180.





| 5.7.5 | `What services cost more than $1,000?` | MRI Single Region ($1,200) — only one | Не включает CT ($900) |
The cost for an MRI of a single region is $1,200.




| 5.7.6 | `Tell me about procedures that DON'T involve blood` | ECG, suturing, wound cleaning — maybe | Не включает blood draw |
For your procedure, we will use a sterile technique for suturing, applying a local anesthetic first. The wound will be cleaned with saline irrigation, and debridement will be performed if necessary. Additionally, a 12-lead ECG will be conducted, with electrodes placed on your chest and limbs, taking about 5 minutes to complete.





### 5.8 Aggregation & Multi-Hop Correctness

| # | Query | Correct Behavior | Failure Mode |
|---|-------|-----------------|--------------|
| 5.8.1 | `What vaccines are available and how much do they cost?` | Flu ($35), COVID (Free), Vaccination Standard ($40) — все 3 | Пропускает одну |
The flu vaccine costs $35, while the COVID-19 vaccine is free.





| 5.8.2 | `How much does a consultation cost?` | HMS: $100/$50 + service_prices.txt: $150 | Даёт только одну цену/источник |
The cost for a standard consultation and treatment is $50.00.




| 5.8.3 | `Tell me about Mark Bolmer` | "Physician Assistant. A highly trained, nationally certified, and state-licensed healthcare professional who practices medicine with varying degrees of autonomy." — из HMS | Создаёт связи/детали не из контекста |
I'm sorry, but I don't have the information you're looking for.
если Mr то также не знает





| 5.8.4 | `What imaging services do you offer and how much do they cost?` | ECG ($120), X-Ray Single ($110), X-Ray Multi ($180), Ultrasound ($250), MRI ($1,200), CT ($900) — из service_prices.txt | Fusion error: добавляет несуществующие связи |
Here are the costs for the imaging services available: a single view X-Ray is $110, a multi view X-Ray is $180, an ultrasound costs $250, a single region MRI is $1,200, and a CT scan is $900.




| 5.8.5 | `What are the costs and procedure details for an ECG?` | Procedure: "12-lead, electrodes on chest and limbs, 5 minutes" (treatment_guide.pdf). Price: $120 (service_prices.txt). Two sources. | Использует только один источник или смешивает неверно |
The cost of a 12-lead electrocardiogram (ECG), which involves placing electrodes on the chest and limbs and takes about 5 minutes, is $120.




### 5.9 Source & Citation Accuracy

| # | Сценарий | Steps | Expected |
|---|----------|-------|----------|
| 5.9.1 | ✅ Source for exosome price | 1. Запросить `How much is exosome treatment?` | Источник = "test" file (не service_prices.txt) |
The cost of exosome treatments varies based on the areas being treated. For a full face and neck, the price is $850 or $2200. For treatment of just the face, neck, or chest, it costs $600 or $1550. For large body areas, the cost is $1200 or $3200.
Source: test
§ How Much Does It Cost?
Match 75%
# How Much Does It Cost?

The cost of exosomes is dependent on what areas are being treated.

skinpen micro-needling + exosomesFull face + neck $850 (1) $2200 (3)Face or neck or chest $600 (1) $1550 (3)Body large area $1200 (1) $3200 (3)Body medium a…



| 5.9.2 | ✅ Source for procedure | 1. Запросить `How is an ECG performed?` | Источник = treatment_guide.pdf (не HMS) |
The ECG performed was a 12-lead test, with electrodes placed on the chest and limbs, and it took 5 minutes to complete.
source: treatment_guide.pdf






| 5.9.3 | ✅ Source for practitioner | 1. Запросить `Who is Mark Bolmer?` | Источник = HMS (hms-practitioner-...) |
I'm sorry, but I don't have the information you're looking for.
source: hms-practitioner-1968050041637580157.txt, match 32%



| 5.9.4 | ✅ Source for clinic | 1. Запросить `Where is your clinic?` | Источник = HMS (hms-clinic-...) |
It appears that you are inquiring about a location in Kuala Lumpur, which is the capital city of Malaysia, not Australia. If you need specific information about Kuala Lumpur or its relation to Australia, please provide more details.




| 5.9.5 | ✅ Cross-source non-confusion | 1. Запросить `How much does Lisa Lu charge?` | HMS practitioners не содержит цен — только титул. Не смешивать с ценами из service_prices.txt |
I'm sorry, but I don't have the information you're looking for.



| 5.9.6 | ✅ Correct section attribution | 1. Запросить `What infection control measures do you use?` | Section = "INFECTION CONTROL" (не "COMMON PROCEDURES") |
To ensure safety and prevent infection, practice hand hygiene before and after every patient contact. Always wear gloves for all procedures, and use a mask and face shield during aerosolizing procedures. Disinfect surfaces with an EPA-registered disinfectant between patients, and dispose of sharps in puncture-resistant containers immediately after use.
source: treatment_guide.pdf



### 5.10 Noise Robustness & Semantic Boundaries

| # | Сценарий | Steps | Expected |
|---|----------|-------|----------|
| 5.10.1 | ✅ Distractor rejection | 1. Запросить `What is the cost of a follow-up visit?` | Должен найти Follow-up Visit ($75) из service_prices.txt, не перепутать с Initial consultation ($100) из HMS |
The cost for a follow-up visit is $75.



| 5.10.2 | ✅ Semantic similarity ≠ answer | 1. Запросить `How long does it take to get blood test results?` | "I don't know" — процедура взятия есть, времени результатов нет |
I'm sorry, but I don't have the information you're looking for.




| 5.10.3 | ✅ Partial info boundary | 1. Запросить `How do I prepare for a blood draw?` | "Standard venipuncture, 3-5 minute procedure" — только процедура, не fasting/prep |
I'm sorry, but I don't have the information you're looking for.



| 5.10.4 | ✅ Implication avoidance | 1. Запросить `Can I get a blood test without insurance?` | "Insurance information is verified before the appointment begins" — не сказано, что требуется. Ответ должен быть из контекста |
I'm sorry, but I don't have the information you're looking for.




| 5.10.5 | ✅ Non-existent entity | 1. Запросить `Is there a pediatrician on staff?` | No pediatrician in KB — "I don't know" (даже если Lisa Lu MD could be) |
I'm sorry, but I don't have the information you're looking for.



| 5.10.6 | ✅ Absent attribute | 1. Запросить `What languages do your practitioners speak?` | Not in KB — "I don't know" |
I'm sorry, but I don't have the information you're looking for.




### 5.11 Overconfidence & Speculation

| # | Сценарий | Steps | Expected |
|---|----------|-------|----------|
| 5.11.1 | ✅ No speculation on pricing | 1. Запросить `Is there a discount for multiple exosome treatments?` | "A series of 3-6 treatments is recommended" — не придумывать скидку |
The total amounts are $2200 and $1550, both associated with the number 3.



| 5.11.2 | ✅ No speculation on availability | 1. Запросить `Can I get an MRI today?` | "I don't have this information" |
I'm sorry, but I don't have the information you're looking for.



| 5.11.3 | ✅ No temporal speculation | 1. Запросить `When was the treatment guide last updated?` | КБ: "Last updated: June 2026" — OK. Если не видно даты — "I don't know" |
I'm sorry, but I cannot provide a final answer without the detailed analysis you mentioned. Please provide the text you would like me to synthesize.



| 5.11.4 | ✅ Comparative without context | 1. Запросить `Is exosome therapy better than laser?` | В КБ нет сравнения — "I don't have this information" |
I'm sorry, but I don't have the information you're looking for.



| 5.11.5 | ✅ Causal without source | 1. Запросить `Does exosome therapy cause cancer?` | В КБ нет — "I don't have this information" (не говорить "no evidence" из общего знания) |
I'm sorry, but I don't have the information you're looking for.




### 5.12 Robustness — Multi-Turn & Repetition

| # | Сценарий | Steps | Expected |
|---|----------|-------|----------|
| 5.12.1 | ✅ Deterministic output | 1. Запросить `How much is an annual physical exam?` 3 раза подряд | Все 3 ответа идентичны ($250) |
1. The cost of an annual physical exam is $250. 2. The cost of an annual physical exam is $250. 3. The cost of an annual physical exam is $250.


| 5.12.2 | ✅ Order independence | 1. Запросить `What services do you offer?` <br>2. Потом `Where is your clinic?` <br>3. Потом опять `What services do you offer?` | Первый и третий ответ идентичны |
1. I'm sorry, but I don't have the information you're looking for. source: service_prices.txt
Match 39%
SERVICE PRICE LIST — Effective January 2026

General Consultation: $150
Follow-up Visit: $75... 

2. It appears that you are inquiring about a location in Kuala Lumpur, Malaysia, specifically in the WP Kuala Lumpur area. If you need more specific information or details about this location, please let me know!

3. I'm sorry, but I don't have the information you're looking for.


| 5.12.3 | ✅ Different phrasing, same answer | 1. `Cost of MRI` <br>2. `MRI price` <br>3. `How much for an MRI?` | Все три находят MRI ($1,200) |
1. The cost for an MRI of a single region is $1,200. 2. I'm sorry, but I don't have the information you're looking for. source: catalog-import_20260523_093243.csv
§ Catalog
Match 26%
Product: Wireless Ergonomic Mouse
SKU/ID: ergo-mouse-100
Category: Electronics
Price: 49.99 USD    (!!! это что то из очень старого чего уже не должно быть в базе - удалял) 3. The cost for an MRI of a single region is $1,200. 


---

## 6. Cross-Feature & Integration

| # | Сценарий | Precondition | Steps | Expected |
|---|----------|-------------|-------|----------|
| 6.1 | ✅ Tab switch сохраняет состояние | На Documents выбран folder | 1. Выбрать папку на Documents <br>2. Переключиться на Web Pages <br>3. Вернуться на Documents | Папка сохраняется. Таблица показывает файлы этой папки. |
| 6.2 | ✅ Tab switch очищает polls | Documents poll активен | 1. Переключить на Practice | _idDocPoll остановлен. _idWpPoll не запущен (был остановлен на switch). |
| 6.3 | ✅ URL hash routing | — | 1. Открыть `/admin/knowledge#webpages` | Открыт Web Pages tab. |
| 6.4 | ✅ Hash change | Открыт Documents | 1. Ввести `#practice` в адресной строке | Переключение на Practice tab. |
| 6.5 | ✅ Role-based tab visibility | Пользователь role=staff (без owner/manager) | 1. Открыть страницу | Табы скрыты (data-role). |
| 6.6 | ✅ Activity log | Выполнены действия | 1. Посмотреть `/knowledge/activity` | События: file_uploaded, url_imported, url_deleted, hms_synced и т.д. |
| 6.7 | ✅ Cleanup orphan chunks | Есть осиротевшие чанки | 1. POST `/knowledge/cleanup` | Orphans удалены. Duplicates удалены. |

---

## 7. UI/UX Quality

### 7.1 Responsiveness & Layout

| # | Сценарий | Steps | Expected |
|---|----------|-------|----------|
| 7.1.1 | ✅ Page-desc subtitle | 1. Посмотреть заголовок | "Retrieval-Augmented Generation technology allows the neural network to search for the necessary information in external sources before answering a question." |
| 7.1.2 | ✅ Tab bar иконки | 1. Посмотреть на табы | Каждый таб имеет SVG иконку (doc, globe, hospital). Иконки 16x16, currentColor. |
| 7.1.3 | ✅ Scrollbar стабилен | 1. Открыть/закрыть модалку | Страница не дёргается (scrollbar-gutter: stable). |
| 7.1.4 | ✅ Toast position | 1. Выполнить действие с toast | Toast в правом верхнем углу. Анимация fade+slide. Через 3с исчезает. |
| 7.1.5 | ✅ Skeleton загрузка | 1. Наблюдать при переходе на таб | Каждый таб показывает skeleton (5-6 строк) при загрузке данных. |

### 7.2 Error Handling

| # | Сценарий | Steps | Expected |
|---|----------|-------|----------|
| 7.2.1 | ✅ API error — таблица | 1. Отключить сеть <br>2. Открыть таб | Error row в таблице с сообщением. Не белый экран. |
| 7.2.2 | ✅ API error — toast | 1. Выполнить действие с ошибкой | Toast с сообщением об ошибке. |
| 7.2.3 | ✅ Confirm modal — защита от закрытия | Идёт загрузка (delete) | 1. Нажать вне модалки | Модалка не закрывается. |

### 7.3 Incremental Updates (no full reload)

| # | Сценарий | Steps | Expected |
|---|----------|-------|----------|
| 7.3.1 | ✅ Status change (processing→ready) | 1. Импортировать URL | Статус меняется без скелетона. Таблица не прыгает. |
| 7.3.2 | ✅ Delete (optimistic) | 1. Удалить строку | Строка исчезает без перезагрузки таблицы. |
| 7.3.3 | ✅ Edit save | 1. Сохранить изменения | Строка обновляется без перезагрузки. |
| 7.3.4 | ✅ Duplicate import | 1. Импортировать существующий URL | Таблица не перегружается. Строка подсвечивается. |

---

## 8. Test Environment Checklist

Перед началом тестирования убедиться:

- [ ] PMS подключён (для HMS Data)
- [ ] Есть тестовые файлы: `.txt`, `.pdf`, `.md`
- [ ] Есть тестовые URL (реальные сайты)
- [ ] OpenAI API key валиден
- [ ] ChromaDB запущена
- [ ] Конфиг `config.yaml`: `top_k: 15`, `distance_threshold: 0.85`

## 9. Резюме

| Раздел | Всего сценариев | Критических (🔴) | Must-have (✅) | Nice-to-have (⭐) |
|--------|----------------|-------------------|----------------|-------------------|
| Documents | 30 | 3 | 25 | 2 |
| Web Pages | 39 | 3 | 34 | 2 |
| HMS Data | 22 | 0 | 22 | 0 |
| RAG Simulator | 77 | 0 | 70 | 7 |
| RAG Hallucination Audit | 71 | 10 | 62 | 9 |
| Cross-Feature | 7 | 0 | 7 | 0 |
| UI/UX | 12 | 0 | 12 | 0 |
| **Total** | **258** | **16** | **232** | **18** |

## 10. Типовые дефекты (watchlist)

| # | Проблема | Где | Приоритет |
|---|----------|-----|-----------|
| 1 | Skeleton flash при обновлении статуса | Web Pages (fixed) | closed |
| 2 | Таблица пуста + empty state скрыт | Web Pages (fixed) | closed |
| 3 | Pills разной высоты (border vs no-border) | Web Pages/Documents (fixed) | closed |
| 4 | Confirm modal закрывается до завершения операции | Web Pages delete (fixed) | closed |
| 5 | Timestamp не обновляется при refresh без изменений | Backend (fixed) | closed |
| 6 | Button Import меняет размер при loading | Web Pages (fixed) | closed |
| 7 | Иконки эмодзи вместо SVG | Throughout (fixed) | closed |
| 8 | Орфаны в Chroma после удаления файла | RAG | medium |
| 9 | Semantic cache не включён по умолчанию | RAG | low |
| 10 | Нет индикации processing для документов >30s | Documents | low |
