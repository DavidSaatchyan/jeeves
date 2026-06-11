# План перевода Jeeves в светлую тему

## Дизайн-система

**Стиль**: Минимализм / Swiss Design — чистый, сеточный, много воздуха, ограниченная палитра.

### Цветовая схема (Admin Neutral)

```css
--bg:           #F8FAFC     /* очень светлый серый — фон страницы */
--surface:      #FFFFFF     /* белый — карточки, панели */
--surface2:     #F1F5F9     /* light gray — secondary surface, ховеры */
--border:       rgba(0,0,0,0.07)     /* тонкие рамки */
--border-bright: rgba(0,0,0,0.12)    /* рамки при ховере */
--accent:       #5e6ad2     /* оставить текущий brand (хорошо контрастирует) */
--green:        #16a34a     /* чуть насыщеннее для читаемости */
--red:          #dc2626
--amber:        #d97706
--cyan:         #0891b2
--text:         #1E293B     /* dark slate — основной текст */
--muted:        #64748B     /* серый для второстепенного */
--muted2:       #94A3B8     /* светло-серый для мета-инфы */
```

### Типографика
- Inter (уже подключён) — менять не надо
- Размеры и line-height остаются

### Принципы
- Тени: очень лёгкие `0 1px 3px rgba(0,0,0,0.06)` для карточек
- Ховеры: `rgba(0,0,0,0.03)` вместо `rgba(255,255,255,0.04)`
- Modal scrim: `rgba(0,0,0,0.35)` с `backdrop-filter: blur(4px)`
- Все skeleton/placeholder градиенты: `rgba(0,0,0,0.06)` → `rgba(0,0,0,0.02)`
- Status bar в прогресс-барах: `rgba(0,0,0,0.08)` вместо `var(--border)`

---

## Этапы работ

### Этап 1: Базовые токены — base.html

**Файл**: `api/app/templates/base.html`

**1.1. `:root` — заменить все CSS-переменные** (строки 12-28)
- `--bg`, `--surface`, `--surface2`
- `--border`, `--border-bright`
- `--text`, `--muted`, `--muted2`
- semantic colors (`--green`, `--red`, etc.)

**1.2. `body`** (строка 30)
- `background: var(--bg)` — подхватит новое значение
- `color: var(--text)` — подхватит

**1.3. Sidebar `aside`** (строка 34)
- Фон: `background: var(--surface)` вместо градиента с тёмным
- `border-right: 1px solid var(--border)` — подхватит
- `.brand` секция: убрать тёмный градиент или заменить на light
- `.nav-link.active` — `rgba(94,106,210,0.08)` вместо `rgba(94,106,210,0.1)`

**1.4. Карточки `.card`** (строка 65)
- `background: var(--surface)` с лёгкой тенью
- Ховер: `box-shadow: 0 2px 8px rgba(0,0,0,0.06)`

**1.5. Формы** (строки 71-78)
- `background: var(--surface2)` для полей ввода
- `border-color: var(--border)` 
- focus: `box-shadow: 0 0 0 3px rgba(94,106,210,0.15)` (светлее)

**1.6. Кнопки** (строки 81-98)
- `button, .btn`: `background: var(--surface2)` с `color: var(--text)`
- `.ghost`: `background: transparent`, `border: 1px solid var(--border)`
- `.ghost:hover`: `background: rgba(0,0,0,0.03)`
- `.accent`: `background: var(--accent)`, `color: #fff` (без изменений)

**1.7. Таблицы** (строки 101-105)
- `th`: `color: var(--muted2)`, `border-bottom: 1px solid var(--border)`
- `tr:hover td`: `background: rgba(0,0,0,0.02)`

**1.8. Pills/Бейджи** (строки 108-116)
- `.pill.ok`: `background: rgba(22,163,74,0.08)`, `border: 1px solid rgba(22,163,74,0.2)`
- `.pill.err`: `background: rgba(220,38,38,0.08)`
- Все hardcoded `rgba(255,255,255,x)` → `rgba(0,0,0,x)` с соответствующими значениями

**1.9. Stat cards** (строки 121-126)
- `.stat`: `background: var(--surface)`, тень вместо `rgba(255,255,255,0.02)`

**1.10. Help box** (строка 129)
- `background: var(--surface)`, `border-left: 3px solid var(--accent)`

**1.11. Drop zone** (строка 136)
- `border: 2px dashed var(--border)`
- `.drop:hover`: `border-color: var(--accent)`, `background: rgba(99,102,241,0.03)`

**1.12. Modal overlay** (строка 199)
- `background: rgba(0,0,0,0.35)` (было `rgba(0,0,0,.65)`)

**1.13. Channel tabs** (строки 206-224)
- `.ch-tab.active`: `background: var(--surface)` (было `var(--surface)` на тёмном — работает)
- `.ch-tab:hover`: `background: rgba(0,0,0,0.03)`

**1.14. Step number** (строка 168)
- `.step-num`: `background: var(--accent)`, `color: #fff` (было `#fff` на `--bg`)

**1.15. Onboarding wizard** (строки 237-251)
- `.ob-wizard`: `background: var(--surface)`
- `.ob-step-pending`: `background: var(--surface2)`, `border: 1px solid var(--border)`

**1.16. Timeline / Funnel / Status bar** (строки 227-256)
- Все `rgba(255,255,255,x)` → `rgba(0,0,0,x)`

**1.17. HMS components** (строки 281-308)
- `.hms-header`: `background: var(--surface)`
- `.hms-global-status.hms-ok`: `background: rgba(22,163,74,0.06)`
- `.hms-global-status.hms-err`: `background: rgba(220,38,38,0.06)`
- `.hms-metrics`: `background: var(--surface)`

**1.18. KB tabs** (строки 275-278)
- `.kb-tab.active`: `background: var(--surface)`
- `.kb-tab:hover`: `background: rgba(0,0,0,0.03)`

**1.19. Skeleton/Shimmer** (зависит от контекста — в основном в knowledge.html)
- Градиент: `rgba(0,0,0,0.06)` → `rgba(0,0,0,0.02)` → `rgba(0,0,0,0.06)`

**1.20. Ссылки** (строка 160)
- `a`: `color: var(--accent)` для обычных ссылок (кроме навигации)
- sidebar ссылки оставить как есть (навигация)

---

### Этап 2: Inbox — inbox.css

**Файл**: `api/app/static/css/inbox.css`

**2.1. Все `rgba(255,255,255,0.0x)` → `rgba(0,0,0,0.0x)`**:
- `.inbox-conv:hover`: `rgba(0,0,0,0.03)` (было `rgba(255,255,255,0.03)`)
- `.inbox-conv.active`: `rgba(94,106,210,0.06)` (было `rgba(94,106,210,0.08)`)
- `.inbox-conv + .inbox-conv`: `rgba(0,0,0,0.03)` (было `rgba(255,255,255,0.03)`)
- `.inbox-status-tab:hover`: `rgba(0,0,0,0.03)` 
- `.inbox-detail-header .actions button:hover`: `rgba(0,0,0,0.03)`
- `.canned-item:hover`: `rgba(94,106,210,0.05)`
- `.profile-close:hover`: `rgba(0,0,0,0.04)`
- `.profile-conv-item`: `rgba(0,0,0,0.03)` вместо `rgba(255,255,255,0.03)`

**2.2. Тени**:
- `.canned-popup`: `box-shadow: 0 4px 20px rgba(0,0,0,0.12)` (было `0 -4px 20px rgba(0,0,0,0.3)`)
- `.inbox-profile`: `box-shadow: -4px 0 16px rgba(0,0,0,0.08)` (было `rgba(0,0,0,0.2)`)
- `.inbox-toast`: `box-shadow: 0 4px 12px rgba(0,0,0,0.12)` 

**2.3. Separator `msg-date-sep::after`**:
- `background: var(--border)` — подхватит

**2.4. System message bubble**:
- `.msg-row.system .msg-bubble`: `background: rgba(0,0,0,0.02)`, `border: 1px dashed var(--border)`

**2.5. Notes area**:
- `.note-item`: `background: var(--surface2)`, `border-left: 2px solid var(--amber)`

---

### Этап 3: Страницы админ-панели (агенты, знания, интеграции, настройки)

**Файлы**:
- `api/app/templates/agents_list.html`
- `api/app/templates/agent_detail.html`
- `api/app/templates/knowledge.html`
- `api/app/templates/integrations_hub.html`
- `api/app/templates/settings_team.html`
- `api/app/templates/settings_billing.html`
- `api/app/templates/settings_logs.html`
- `api/app/templates/inbox.html`

**3.1. Общее для всех**: заменить все вхождения
- `rgba(255,255,255,0.02)` → `var(--surface)` или `rgba(0,0,0,0.02)`
- `rgba(255,255,255,0.03)` → `rgba(0,0,0,0.03)`
- `rgba(255,255,255,0.04)` → `rgba(0,0,0,0.03)`
- `rgba(255,255,255,0.06)` → `rgba(0,0,0,0.04)`
- `rgba(0,0,0,0.2)` → `rgba(0,0,0,0.08)` (тени)
- `rgba(0,0,0,0.3)` → `rgba(0,0,0,0.1)` (тени)

**3.2. Agent Detail** — hardcoded:
- toast `box-shadow: 0 4px 12px rgba(0,0,0,.3)` → `rgba(0,0,0,0.1)`
- playground background: `var(--surface2)`
- `.msg.assistant`: `background: var(--surface)`, `border: 1px solid var(--border)`

**3.3. Knowledge** — самый объёмный файл. Ключевые группы:
- `.kb-sidebar`, `.kb-stat`, `.kb-summary` — фоны на `var(--surface)`
- `.kb-folder-item:hover`: `rgba(0,0,0,0.03)`
- `.kb-folder-item.active`: `rgba(94,106,210,0.08)`
- `.kebab-menu`: `background: var(--surface)`, `box-shadow: 0 8px 24px rgba(0,0,0,0.1)`
- `.kb-chunk`: `background: rgba(0,0,0,0.02)`
- `skeleton` градиенты
- `.hms-table th`: `background: rgba(0,0,0,0.02)`
- `.hms-table tr:hover td`: `background: rgba(0,0,0,0.02)`
- `.sim-section`: `background: var(--surface)`
- `.sim-input`: `background: var(--surface2)`
- `.sim-source-header`: `background: rgba(0,0,0,0.02)`
- `.sim-chunk-item:hover`: `rgba(0,0,0,0.02)`
- `.import-bar`: `background: var(--surface)`
- `.hms-onboarding-banner`: `background: rgba(99,102,241,0.06)`
- `.kb-toast`: `box-shadow: 0 8px 24px rgba(0,0,0,0.08)`
- `.kb-bar-track`: `background: rgba(0,0,0,0.06)` — прогресс-бар
- `.kb-input`: `background: var(--surface2)`
- `.kb-folder-count`: `background: rgba(0,0,0,0.04)`

**3.4. Integrations Hub**:
- `.hub-card`: `background: var(--surface)`, `box-shadow: 0 1px 2px rgba(0,0,0,0.06)`
- `.hub-card:hover`: `box-shadow: 0 4px 16px rgba(0,0,0,0.08)`
- `.hub-card.connected`: `border-left: 3px solid var(--green)`
- `snippet-box`: `background: var(--surface2)`, `color: var(--text)`
- `.hint-steps-inner`: `background: var(--surface2)`
- `.skel-shimmer`: градиент через `rgba(0,0,0,0.03)`

**3.5. Login page**:
- `.auth-page`: `background: radial-gradient(ellipse at 50% 0%, rgba(99,102,241,0.04) 0%, transparent 60%)`
- `.auth-card`: `background: var(--surface)`
- `.auth-tabs`: `background: var(--surface2)`
- `.auth-page-footer`: `background: rgba(255,255,255,0.85)`, `backdrop-filter: blur(12px)`
- `.auth-page-footer a`: `color: var(--muted2)`
- `.spinner`: `border: 2px solid rgba(0,0,0,0.1)`, `border-top-color: var(--accent)`

**3.6. Settings Billing**:
- `plan-card.selected`: `border-color: var(--accent)`

**3.7. Settings Logs**:
- Minimal hardcoded values — mostly uses CSS vars already

---

### Этап 4: Лендинг — landing.html

**Файл**: `api/app/templates/landing.html` (1545 строк, standalone)

**4.1. `:root`** (строки 11-28) — полная замена на светлую палитру:
```css
--bg: #FAFAFA
--surface: #FFFFFF
--surface2: #F3F4F6
--accent: #5e6ad2
--accent2: #7c6fcf
--accent3: #0891b2
--border: rgba(0,0,0,0.06)
--border-bright: rgba(0,0,0,0.10)
--text: #1E293B
--muted: #6B7280
--muted2: #9CA3AF
```

**4.2. Nav** (строка 34)
- `background: rgba(255,255,255,0.9)`, `backdrop-filter: blur(24px)`, `border-bottom: 1px solid var(--border)`
- `.btn-nav`: `background: var(--accent)`, `color: #fff`

**4.3. Hero** (строки 45-136)
- `.hero-grid`: `rgba(0,0,0,0.03)` для линий сетки
- `.hero-orb`: существенно уменьшить opacity:
  - `.o1`: `opacity: .06`
  - `.o2`: `opacity: .04`
  - `.o3`: `opacity: .04`
- `.badge`: `background: rgba(94,106,210,0.06)`, `border: 1px solid rgba(94,106,210,0.15)`
- `.hero-text h1 .hl`: градиент на тёмных тонах (dark slate → accent) для контраста на белом
- `.hero-feat`: `color: var(--muted)`
- `.hero-text p`: `color: var(--muted)`
- `.btn-primary`: `background: var(--accent)`, `color: #fff` (инвертировать!)
- `.btn-secondary`: `background: transparent`, `border: 1px solid var(--border)`, `color: var(--text)`
- `.btn-secondary:hover`: `background: rgba(0,0,0,0.03)`

**4.4. Phone mockup** (строки 84-136)
- `.phone-frame`: 
  - Фон: `#F0F2F5` (светло-серый корпус)
  - Тень: `-15px 25px 50px rgba(0,0,0,0.15)`, `15px -8px 30px rgba(255,255,255,0.8)`
  - `box-shadow` inset: `inset 0 2px 4px rgba(255,255,255,0.8)`, `inset 0 -2px 4px rgba(0,0,0,0.05)`
- `.phone-screen`: `background: var(--bg)`
- `.phone-dynamic-island`: `background: #1E293B`
- `.phone-status`: `color: var(--text)`
- `.phone-nav-bar`: `background: var(--surface2)`, `border-bottom: 1px solid var(--border)`
- `.phone-body`: `background: linear-gradient(180deg, var(--bg) 0%, var(--surface) 100%)`
- `.msg.bot .msg-bubble`: `background: var(--surface2)`, `border: 1px solid var(--border)`, `color: var(--text)`
- `.msg.user .msg-avatar`: `background: var(--surface2)`, `border: 1px solid var(--border)`
- `.phone-input`: `background: var(--surface2)`, `border-top: 1px solid var(--border)`
- `.phone-input-field`: `background: var(--surface)`, `border: 1px solid var(--border)`, `color: var(--muted)`

**4.5. RAG Hero** (строки 155-298)
- `.rag-hero`: `background: var(--surface)`, `border: 1px solid var(--border)`
- `.rag-badge`: `background: rgba(94,106,210,0.06)`
- Все doc cards: `background: var(--surface2)`, `border: 1px solid var(--border)`
- `doc-line`: `rgba(0,0,0,0.08)` вместо `rgba(255,255,255,0.5)`
- `.rag-embed-output`: `background: var(--surface2)`, `border: 1px solid rgba(94,106,210,0.1)`
- `.rag-embed-header`: `background: rgba(94,106,210,0.04)`
- `.rag-funnel-top`: `background: var(--surface2)`
- `.rag-answer-box`: `background: var(--surface2)`, `border: 1px solid var(--border)`
- `.rag-answer-header`: `background: rgba(0,0,0,0.03)`

**4.6. Stats row** (строки 301-305)
- `.stat-num`: `color: var(--text)`
- `.stat-label`: `color: var(--muted)`
- `.stat-val`: `color: var(--muted2)`

**4.7. Capabilities Bento** (строки 308-353, 952-1023)
- `.cap-b`: `background: var(--surface)` with light shadow
- `.cap-mono-block`: `background: rgba(0,0,0,0.02)`, `border: 1px solid var(--border)`
- `.cap-audit-table thead th`: `background: rgba(0,0,0,0.03)`
- `.cap-audit-table tbody td`: `background: rgba(0,0,0,0.01)`

**4.8. Channels Circuit Board** (строки 365-458, 1036-1130)
- `.cb-pcb`: `background: linear-gradient(160deg, #F8FAFC 0%, #FFFFFF 50%, #F8FAFC 100%)`
- `.cb-tile`: `background: var(--surface)`, `border: 1px solid var(--border)`
- `.cb-tile.active svg`: убрать `drop-shadow`
- `.cb-tile.cb-jeeves`: `background: linear-gradient(145deg, var(--surface) 0%, var(--surface2) 50%, var(--surface) 100%)`
- Все tile SVG цвета оставить (brand accent как есть)

**4.9. Terminal / How it works** (строки 460-485)
- `.deploy-terminal`: `background: var(--surface)`
- `.dt-header`: `background: rgba(0,0,0,0.03)`
- `.dt-body`: тёмный терминал не работает на светлом.
  - **Решение**: имитировать "терминал" в светлой теме с белым фоном, тёмным текстом и рамкой
  - Фон `.deploy-terminal` → `var(--bg)`
  - `.dt-header` → `var(--surface2)`
  - `.dt-cmd .dt-prompt` → `var(--accent)`

**4.10. Pricing** (строки 488-503, 1169-1222)
- `.price-card`: `background: var(--surface)`, `border: 1px solid var(--border)`
- `.price-card.featured::before`: `background: var(--accent)`, `color: #fff`
- `.p-btn.primary`: `background: var(--accent)`, `color: #fff`

**4.11. CTA + Footer** (строки 506-516, 1227-1245)
- `footer`: `border-top: 1px solid var(--border)`
- `.footer-links a`: `color: var(--muted2)`

**4.12. Mobile responsive** (строки 518-671)
- Все `!important` значения адаптировать под светлую тему (те же замены)

---

### Этап 5: Статические страницы — terms.html, privacy.html

**Файлы**: `api/app/templates/terms.html`, `api/app/templates/privacy.html`

**5.1. `:root`**:
```css
--bg: #FAFAFA
--surface: #FFFFFF
--border: rgba(0,0,0,0.08)
--accent: #5e6ad2
--text: #1E293B
--muted: #6B7280
--muted2: #9CA3AF
```

**5.2. `body`**: `background: var(--bg)`, `color: var(--text)`

---

## Итого: файлы к изменению

| № | Файл | Строк | Сложность | Hardcoded значений |
|---|------|-------|-----------|-------------------|
| 1 | `api/app/templates/base.html` | 447 | Высокая | ~50 мест (весь :root + 20+ компонентов) |
| 2 | `api/app/static/css/inbox.css` | 181 | Средняя | ~35 мест (ховеры, тени, разделители) |
| 3 | `api/app/templates/agents_list.html` | 117 | Низкая | ~5 мест |
| 4 | `api/app/templates/agent_detail.html` | 437 | Средняя | ~10 мест (плейграунд, тосты) |
| 5 | `api/app/templates/knowledge.html` | 1779 | Очень высокая | ~80+ мест (самый большой файл) |
| 6 | `api/app/templates/integrations_hub.html` | 880 | Высокая | ~30 мест (карточки, сниппеты, шедовы) |
| 7 | `api/app/templates/login.html` | 325 | Средняя | ~10 мест (auth page, футер) |
| 8 | `api/app/templates/settings_billing.html` | 194 | Низкая | ~2 места |
| 9 | `api/app/templates/settings_logs.html` | 96 | Низкая | ~0 (чистые CSS-вары) |
| 10 | `api/app/templates/settings_team.html` | 125 | Низкая | ~0 |
| 11 | `api/app/templates/inbox.html` | 72 | Низкая | ~0 |
| 12 | `api/app/templates/dashboard.html` | 12 | Низкая | ~0 |
| 13 | `api/app/templates/landing.html` | 1545 | Очень высокая | ~100+ мест (полная переработка) |
| 14 | `api/app/templates/terms.html` | 91 | Низкая | ~1 (:root) |
| 15 | `api/app/templates/privacy.html` | 106 | Низкая | ~1 (:root) |

**Приоритет выполнения**:
1. **base.html** — основа, от него зависят все шаблоны
2. **landing.html** — самый большой и сложный
3. **knowledge.html** — много hardcoded значений
4. **integrations_hub.html** — карточки и модалки
5. **inbox.css** — чат
6. **agent_detail.html** — плейграунд
7. **login.html** — страница входа
8. **agents_list.html** — простая сетка
9. **terms.html + privacy.html** — минимальные правки
10. Остальные — точечные исправления

---

## Чек-лист качества

Перед завершением каждого файла проверить:

**Контрастность**
- [ ] body text: `#1E293B` на `#F8FAFC` — контраст 15.4:1 (> 4.5 ✓)
- [ ] muted text: `#64748B` на `#F8FAFC` — контраст 5.8:1 (> 4.5 ✓)
- [ ] muted2 text: `#94A3B8` на `#F8FAFC` — контраст 3.6:1 (для мелкого текста норм)
- [ ] accent text: `#5e6ad2` на `#F8FAFC` — контраст 5.2:1 (> 4.5 ✓)

**Состояния**
- [ ] hover на карточках — лёгкая тень + `rgba(0,0,0,0.03)`
- [ ] focus на полях ввода — синее свечение с opacity 0.15
- [ ] disabled кнопки — opacity 0.5
- [ ] active nav link — accent background 8%

**Тени**
- [ ] карточки: `0 1px 3px rgba(0,0,0,0.06)`
- [ ] модалки: `0 8px 24px rgba(0,0,0,0.1)`
- [ ] дропдауны: `0 4px 12px rgba(0,0,0,0.08)`

**Визуальная иерархия**
- [ ] белые карточки (`--surface: #FFFFFF`) на светлом фоне (`--bg: #F8FAFC`)
- [ ] разделители (`--border`) достаточно заметны
- [ ] боковая панель визуально отделена от контента
- [ ] статусные цвета (green/red/amber) читаются на белом фоне
