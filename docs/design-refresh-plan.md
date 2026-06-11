# Design Refresh: Эффектный минимализм

## Концепция

**Minimalism & Swiss Style** — чистый, сеточный, много воздуха, ограниченная палитра.
Контент — король. Каждая линия и отступ осмысленны.

**Для кого**: Клиники — белый, чистый, стерильный, профессиональный.
**Тема**: Только светлая. Никакого dark mode в MVP для B2B clinic SaaS.
**Ключевые слова**: лёгкость, глубина, контраст, премиальность, консистентность.

---

## Цветовая палитра

```css
--bg:           #F4F6F9     /* тёплый светло-серый — фон страницы */
--surface:      #FFFFFF     /* белый — карты, панели, сайдбар */
--surface2:     #EDEFF3     /* light gray — secondary surface, ховеры */
--accent:       #4f46e5     /* Indigo-600 — brand (оставляем текущий) */
--accent-hover: #4338ca     /* Indigo-700 */
--accent-subtle: rgba(79,70,229,0.08)  /* accent на surface */
--green:        #16a34a     /* Green-600 */
--red:          #dc2626     /* Red-600 */
--amber:        #d97706     /* Amber-600 */
--cyan:         #0891b2     /* Cyan-600 */
--text:         #0F172A     /* Slate-900 — основной текст */
--muted:        #475569     /* Slate-600 — второстепенный */
--muted2:       #64748B     /* Slate-500 — мета-инфа */
--border:       rgba(0,0,0,0.07)     /* тонкие рамки */
--border-bright: rgba(0,0,0,0.14)    /* рамки при ховере/active */
--scrim:        rgba(0,0,0,0.32)     /* modal overlay */
```

**Важно**: `--accent` остаётся `#4f46e5` (был разброс — `#5e6ad2` в legal, `#4f46e5` в base). Унифицировать.

---

## Типографика

- **Font**: Inter (уже подключён) — 400, 500, 600, 700, 800
- **База**: `15px`, line-height `1.65`
- **Моно**: `'SF Mono', ui-monospace, Consolas, monospace`

### Scale (новая)

| Элемент | Размер | Weight | Letter-spacing |
|---------|--------|--------|----------------|
| Page title (h1) | `22px` | `700` | `-0.3px` |
| Section header (h2) | `13px` | `600` | `0.3px` |
| Card title | `15px` | `600` | `0` |
| Body | `14px` | `400` | `0` |
| Small/meta | `12px` | `500` | `0` |
| Fine print | `11px` | `500` | `0` |
| Stat number | `28px` | `700` | `-0.5px` |
| Badge | `10px` | `600` | `0.3px` |

**Изменения относительно текущего**:
- h2 был `12px uppercase 700` → становится `13px 600` (без uppercase — современнее, чище)
- Stat number был `24px` → `28px` для большего визуального веса
- Добавлен Card title: `15px 600`

---

## Spacing Scale (4px grid)

```css
--space-1:  4px;
--space-2:  8px;
--space-3:  12px;
--space-4:  16px;
--space-5:  20px;
--space-6:  24px;
--space-8:  32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
```

**Применение**:
- Card padding: `--space-6` (24px)
- Section margin-bottom: `--space-8` (32px)
- Grid gap: `--space-4` (16px) или `--space-3` (12px)
- Form field padding: `--space-3` `--space-4` (12px 16px)
- Button padding: `--space-2` `--space-4` (8px 16px)
- Avatar: `--space-8` (32px)
- Sidebar width: `220px` (оставить)

---

## Shadow Scale

```css
--shadow-sm:  0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
--shadow-md:  0 4px 12px rgba(0,0,0,0.07);
--shadow-lg:  0 8px 24px rgba(0,0,0,0.10);
--shadow-xl:  0 16px 40px rgba(0,0,0,0.14);
```

**Применение**:
- Cards: `--shadow-sm`
- Cards on hover: `--shadow-md` + `translateY(-1px)`
- Dropdowns / kebab: `--shadow-md`
- Modals: `--shadow-lg`
- Toasts: `--shadow-md`
- Tooltips: `--shadow-md`

---

## Border-Radius

```css
--radius-sm: 6px;    /* кнопки, инпуты, бейджи */
--radius-md: 8px;    /* карты, модалки, панели */
--radius-lg: 12px;   /* крупные карты, auth card */
--radius-xl: 14px;   /* большие модалки */
--radius-full: 9999px;  /* аватары, тоглы */
```

**Важно**: Убрать разнобой (5px, 10px, 4px, 12px, 6px, 14px, 50%). Везде использовать токены.

---

## Animation

```css
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);       /* enter — плавный вылет */
--ease-in: cubic-bezier(0.4, 0, 1, 1);             /* exit */
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);  /* микро-пружина */
--duration-fast: 150ms;
--duration-normal: 250ms;
--duration-slow: 350ms;
```

**Применение**:
- Hover transitions: `--duration-fast` `--ease-out`
- Card hover lift: `--duration-fast` `--ease-out`
- Modal enter: `--duration-normal` `--ease-spring`
- Page transitions: `--duration-normal` `--ease-out`
- Stagger list items: `50ms` delay between items

**`prefers-reduced-motion`**: Все анимации под `@media (prefers-reduced-motion: no-preference)`.

---

## Этапы работ

### Фаза 0: Архитектура CSS

**Цель**: Единый источник правды для всех стилей.

- [ ] **`static/css/tokens.css`** — все CSS-переменные (цвета, spacing, shadow, radius, animation)
- [ ] **`static/css/base.css`** — layout (sidebar + main), body, типографика, навигация
- [ ] **`static/css/components.css`** — карты, кнопки, формы, таблицы, pills, модалки, skeleton, toasts, badges
- [ ] **`static/css/vendor.css`** — reset, normalize (если нужно)
- [ ] **`static/css/pages/`** — страничные стили:
  - `knowledge.css`
  - `integrations.css`
  - `agent.css`
  - `inbox.css` (переписать существующий)
  - `login.css`
  - `settings.css`
- [ ] **`static/css/landing.css`** — лендинг (сейчас 1500 строк inline)
- [ ] **`static/css/legal.css`** — terms + privacy

**Шаги**:
1. Создать файлы, скопировать туда соответствующие стили из `<style>` блоков
2. Заменить токены на CSS-переменные
3. Подключить через `<link>` в `base.html` (и `landing.html`, `terms.html`)
4. Удалить `<style>` блоки из шаблонов

**Файлы к изменению**: `base.html`, `landing.html`, `terms.html`, `privacy.html`, `knowledge.html`, `integrations_hub.html`, `agent_detail.html`, `inbox.html`, `login.html`, `settings_*.html`

---

### Фаза 1: Визуальная глубина

**Цель**: Превратить плоский интерфейс в многослойный, премиальный.

#### 1.1 Карты и поверхности

- [ ] Добавить `--shadow-sm` на все `.card`
- [ ] Добавить `--shadow-md` + `translateY(-1px)` на `.card:hover`
- [ ] Убрать hardcoded `border` на картах (токен `--border`)
- [ ] `.stat-card`: `background: var(--surface)`, `--shadow-sm`
- [ ] `.hub-card`: `--shadow-sm`, на hover `--shadow-md` + `translateY(-2px)` с `--duration-fast`

#### 1.2 Сайдбар

- [ ] Чистый белый фон (`--surface`) с `border-right: 1px solid var(--border)`
- [ ] Brand section: убрать градиент, оставить лого + название, `border-bottom: 1px solid var(--border)`
- [ ] `.nav-link`: padding `--space-2` `--space-4`, `border-radius: var(--radius-sm)`
- [ ] `.nav-link:hover`: `background: var(--surface2)`
- [ ] `.nav-link.active`: `background: var(--accent-subtle)` + 2px left accent bar
- [ ] Nav иконки: `20px`, `stroke-width: 1.5`, `color: var(--muted2)` → active `var(--accent)`
- [ ] Settings section label: `--space-2` `--space-4`, `13px 600`, `color: var(--muted2)`
- [ ] Sign out: `color: var(--muted2)`, hover `var(--red)`

#### 1.3 Типографика

- [ ] h1: `22px 700 -0.3px` (page titles)
- [ ] h2: `13px 600 0.3px` (section headers — убрать uppercase)
- [ ] Карточные заголовки: `15px 600`
- [ ] Секции h1 + paragraph description: `14px` muted, `max-width: 680px`
- [ ] Убрать h2 uppercase везде (base, knowledge, integrations, settings, agents, agent_detail)

#### 1.4 Кнопки

- [ ] Стандартизировать `border-radius: var(--radius-sm)`
- [ ] `--duration-fast` `--ease-out` на :hover
- [ ] Primary (`.btn.accent`): `background: var(--accent)`, `color: #fff`, hover `var(--accent-hover)`
- [ ] Secondary (`.btn`): `background: var(--surface2)`, `color: var(--text)`, hover `background: color-mix(in srgb, var(--surface2), #000 5%)`
- [ ] Ghost (`.btn.ghost`): `background: transparent`, `border: 1px solid var(--border)`, hover `background: var(--surface2)`
- [ ] Danger (`.btn.danger`): `background: var(--red)`, `color: #fff`
- [ ] `.btn.sm`: `padding: 6px 12px`, `font-size: 12px`
- [ ] `.btn.xs`: `padding: 4px 10px`, `font-size: 11px`

#### 1.5 Таблицы

- [ ] `.table th`: `color: var(--muted2)`, `font-size: 11px`, `font-weight: 600`, `text-transform: uppercase`, `letter-spacing: 0.5px`
- [ ] `.table td`: `padding: var(--space-3) var(--space-4)`
- [ ] `.table tr:hover td`: `background: rgba(0,0,0,0.02)`
- [ ] Унифицировать стили между base table, kb-table, hms-table

#### 1.6 Формы

- [ ] `input, select, textarea`: `background: var(--surface)`, `border: 1px solid var(--border)`, `border-radius: var(--radius-sm)`
- [ ] `input:hover`: `border-color: var(--border-bright)`
- [ ] `input:focus`: `border-color: var(--accent)`, `box-shadow: 0 0 0 3px var(--accent-subtle)`
- [ ] `label`: `font-size: 13px`, `font-weight: 600`, `color: var(--text)`, `margin-bottom: 6px`
- [ ] Placeholder: `color: var(--muted2)`
- [ ] Disabled: `opacity: 0.5`, `cursor: not-allowed`
- [ ] Standarтизировать padding: `--space-3` `--space-4`

#### 1.7 Пустые состояния

- [ ] `.empty-state`: centered, `padding: var(--space-12)`
- [ ] Иконка/иллюстрация: `48-64px`, `color: var(--muted2)`
- [ ] Title: `15px 600`, `color: var(--text)`
- [ ] Description: `13px`, `color: var(--muted)`
- [ ] CTA: `.btn.accent`
- [ ] Применить на всех страницах: inbox ("No conversations"), team ("No team members"), knowledge ("No documents"), logs ("No activity")

---

### Фаза 2: Микро-анимации

**Цель**: Плавные, осмысленные переходы, которые чувствуются как премиум.

- [ ] **Card hover**: `translateY(-1px)` + `--shadow-sm` → `--shadow-md` (150ms)
- [ ] **Modal enter**: scale(0.96) → scale(1) + fade in (250ms ease-spring)
- [ ] **Modal exit**: fade out (150ms ease-in)
- [ ] **Kebab menu**: fade + slide (150ms ease-out)
- [ ] **Toast**: slide-in from right (250ms ease-out)
- [ ] **Page transition**: `opacity: 0` → `1` на `<main>` при навигации (200ms)
- [ ] **Stagger list**: элементы списка появляются с `50ms` задержкой между ними
- [ ] **Tab switch**: underline/indicator slide (200ms ease-out)
- [ ] **Skeleton pulse**: shimmer анимация (только на knowledge, можно расширить)
- [ ] **Button press**: scale(0.97) на `:active` (100ms)
- [ ] **Nav link**: accent bar slide-in на `:hover` (150ms)
- [ ] **Checkbox/toggle**: smooth transition on state change (200ms)

---

### Фаза 3: Доступность (Accessibility)

**Цель**: WCAG AA compliance. Клиники — регулируемая среда.

- [ ] **`:focus-visible`** на всех interactive элементах: `outline: 2px solid var(--accent)`, `outline-offset: 2px`
  - Сейчас focus только на form inputs. Добавить на: buttons, links, nav items, tab items, toggle switches, kebab menu
- [ ] **`:focus-visible`** на `[contenteditable]` (inbox composer, agent playground)
- [ ] **`:focus`** для form inputs: `box-shadow: 0 0 0 3px var(--accent-subtle)` (уже частично есть)
- [ ] **Color contrast**:
  - `--muted: #475569` на `--bg: #F4F6F9` — контраст 6.1:1 (AA ✓)
  - `--muted2: #64748B` на `--bg: #F4F6F9` — контраст 4.5:1 (AA для large text ✓)
  - `--accent: #4f46e5` на `--surface: #FFFFFF` — контраст 6.8:1 (AA ✓)
  - `--text: #0F172A` на `--surface: #FFFFFF` — контраст 17.4:1 (AAA ✓)
- [ ] **`prefers-reduced-motion`**: все анимации под `@media (prefers-reduced-motion: no-preference)`
- [ ] **Skip to main content**: первая фокусная ссылка в `base.html`
- [ ] **`cursor: pointer`** на всех clickable (кнопки, ссылки, tab items, toggle, kebab)
- [ ] **`cursor: not-allowed`** на disabled элементах
- [ ] **Touch targets**: минимум `44x44px` на мобильных (кнопки, иконки, tab items)

---

### Фаза 4: Лендинг (Landing page)

**Цель**: Привести визуальный язык лендинга в соответствие с админкой (сейчас два разных продукта).

- [ ] Переиспользовать те же CSS-переменные, что и в админке (подключить `tokens.css`)
- [ ] Hero: сохранить 3D phone, floating orbs, но сделать аккуратнее
- [ ] Цветовая схема лендинга: та же `--accent: #4f46e5`
- [ ] Nav: `background: rgba(255,255,255,0.85)` + `backdrop-filter: blur(16px)`
- [ ] Кнопки на лендинге: те же стили, что в админке
- [ ] Типографика: те же размеры/веса
- [ ] Формы на лендинге (waitlist, contact): те же стили, что в админке
- [ ] Анимации: сохранить scroll reveal, но унифицировать easing/duration
- [ ] Footer: те же стили, что в админке

---

### Фаза 5: Inbox (Чат)

- [ ] Переписать `inbox.css` с использованием CSS-переменных
- [ ] Убрать все hardcoded цвета и тени
- [ ] Унифицировать hover/active/focus состояния
- [ ] Системные сообщения: `background: var(--surface2)`, `border: 1px dashed var(--border)`
- [ ] Bubble: `border-radius: var(--radius-md)`, asymmetric
- [ ] Timestamp separator: `color: var(--muted2)`, `font-size: 11px`, centered with `::before/after` lines using `var(--border)`
- [ ] Conversation list item hover: `background: rgba(0,0,0,0.02)`
- [ ] Active conversation: `background: var(--accent-subtle)`
- [ ] Avatar colors: 8-color palette (indigo, green, red, amber, cyan, purple, pink, teal) — уже есть, оставить
- [ ] Canned responses popup: `--shadow-lg`, `border-radius: var(--radius-md)`
- [ ] Profile panel: slide-in from right, `--shadow-lg`

---

### Фаза 6: Страницы админки

**Цель**: Визуальная и компонентная консистентность между всеми страницами.

#### 6.1 Knowledge page
- [ ] Переписать `<style>` блок в `pages/knowledge.css`
- [ ] Стандартизировать таблицы (kb-table, hms-table → единый `.table` класс)
- [ ] Kebab menu: `--shadow-md`, `border-radius: var(--radius-sm)`
- [ ] Import bar: `--surface`, `--shadow-sm`
- [ ] Chunks display: `background: var(--surface2)`, `border-radius: var(--radius-sm)`
- [ ] HMS metrics cards: `--shadow-sm`
- [ ] Skeleton/shimmer: через CSS-градиент с токенами

#### 6.2 Integrations Hub
- [ ] Hub cards: `--shadow-sm`, hover `--shadow-md` + `translateY(-2px)`
- [ ] Connected: `border-left: 3px solid var(--green)`
- [ ] Snippet box: `background: var(--surface2)`, `border-radius: var(--radius-sm)`
- [ ] Modal: `--radius-lg`, `--shadow-lg`

#### 6.3 Agent Detail
- [ ] Playground: `background: var(--surface2)`, `border-radius: var(--radius-md)`
- [ ] Message bubble `.assistant`: `background: var(--surface)`, `border: 1px solid var(--border)`
- [ ] Message bubble `.user`: `background: var(--accent)`, `color: #fff`
- [ ] Config tabs: `.tab.active` → `var(--accent)` underline

#### 6.4 Settings pages
- [ ] Team table: стандартная `.table`
- [ ] Billing plan cards: `--shadow-sm`, selected `border-color: var(--accent)`
- [ ] Logs timeline: уже минимальна, проверить токены

#### 6.5 Login page
- [ ] Clean auth card: `--surface`, `--shadow-lg`, `--radius-xl`
- [ ] Tabs: `background: var(--surface2)`, `border-radius: var(--radius-md)`
- [ ] Footer: `background: rgba(255,255,255,0.85)`, `backdrop-filter: blur(12px)`
- [ ] Background: subtle radial gradient `rgba(79,70,229,0.03)` at top

#### 6.6 Agents list
- [ ] Agent cards: `--shadow-sm`, hover `--shadow-md`
- [ ] Toggle switch: smooth transition, `var(--duration-fast)`

---

### Фаза 7: Иконки и визуальные элементы

- [ ] Проверить, что все иконки — SVG (не emoji)
- [ ] Единая stroke width: `1.5px` для nav/icons, `2px` для акцентных
- [ ] Heroicons или Lucide (уже Feather-style — оставить)
- [ ] Убрать inline SVG из шаблонов, где возможно — заменить на `<svg class="icon"><use href="#icon-xxx"/></svg>` (как в knowledge page)
- [ ] Создать `static/icons/symbol-defs.svg` — спрайт всех иконок

---

### Фаза 8: Тестирование и доводка

- [ ] Проверить все страницы на 375px, 768px, 1024px, 1440px
- [ ] Проверить контраст всех цветовых пар (на desktop и mobile)
- [ ] Проверить focus-visible на всех интерактивных элементах
- [ ] Проверить hover/active/disabled состояния
- [ ] Убедиться, что `prefers-reduced-motion` работает
- [ ] `python -c "from app.main import app"` — импорты резолвятся
- [ ] `ruff check` — нет lint ошибок
- [ ] `pytest api/tests/ -v --tb=short` — тесты проходят

---

## Приоритет выполнения

| Приоритет | Фаза | Описание | Файлов | Сложность |
|-----------|------|----------|--------|-----------|
| **P0** | Фаза 0 | Архитектура CSS (tokens, вынос стилей) | 15+ | Высокая |
| **P1** | Фаза 1 | Визуальная глубина (тени, карты, типографика) | 15+ | Высокая |
| **P1** | Фаза 5 | Inbox (чат — ключевой экран) | 2 | Средняя |
| **P2** | Фаза 2 | Микро-анимации | 3-5 | Средняя |
| **P2** | Фаза 6 | Страницы админки (knowledge, integrations, agents) | 8+ | Высокая |
| **P3** | Фаза 3 | Доступность | 3-5 | Средняя |
| **P3** | Фаза 4 | Лендинг | 1 | Средняя |
| **P4** | Фаза 7 | Иконки | 3 | Низкая |
| **P4** | Фаза 8 | Тестирование | — | Средняя |

---

## Чек-лист качества (pre-flight)

### Контрастность
- [ ] body text `#0F172A` на `#F4F6F9` — 15.4:1 (AAA ✓)
- [ ] muted text `#475569` на `#F4F6F9` — 6.1:1 (AA ✓)
- [ ] muted2 text `#64748B` на `#F4F6F9` — 4.5:1 (AA large ✓)
- [ ] accent `#4f46e5` на `#FFFFFF` — 6.8:1 (AA ✓)
- [ ] accent `#4f46e5` на `#F4F6F9` — 5.9:1 (AA ✓)

### Состояния
- [ ] hover на карточках — `--shadow-md` + `translateY(-1px)`
- [ ] hover на кнопках — чуть темнее фон
- [ ] focus на всём — `:focus-visible` outline
- [ ] active на nav — accent background 8% + left bar
- [ ] disabled — opacity 0.5, cursor not-allowed

### Визуальная иерархия
- [ ] белые карты (`--surface`) на сером фоне (`--bg`) читаются как слои
- [ ] разделители (`--border`) достаточно заметны, не доминируют
- [ ] сайдбар визуально отделён от контента
- [ ] статусные цвета (green/red/amber) читаются на белом
- [ ] тени создают depth hierarchy (cards < modals < tooltips)

### Консистентность
- [ ] нет hardcoded hex-цветов (только `var(--xxx)`)
- [ ] все border-radius через токены
- [ ] все spacing через токены
- [ ] все shadows через токены
- [ ] все transition timing через токены
- [ ] нет дублирующихся стилей в разных файлах

---

## Файлы к изменениям

| № | Файл | Строк | Описание |
|---|------|-------|----------|
| 1 | `api/app/static/css/tokens.css` | new | Дизайн-токены |
| 2 | `api/app/static/css/base.css` | new | Layout + типографика + навигация |
| 3 | `api/app/static/css/components.css` | new | Карты, кнопки, формы, таблицы, модалки |
| 4 | `api/app/static/css/pages/knowledge.css` | new | Страница знаний |
| 5 | `api/app/static/css/pages/integrations.css` | new | Интеграции |
| 6 | `api/app/static/css/pages/agent.css` | new | Детали агента |
| 7 | `api/app/static/css/pages/inbox.css` | rewrite | Чат (заменить существующий) |
| 8 | `api/app/static/css/pages/login.css` | new | Страница входа |
| 9 | `api/app/static/css/pages/settings.css` | new | Настройки |
| 10 | `api/app/static/css/landing.css` | new | Лендинг |
| 11 | `api/app/static/css/legal.css` | new | Terms + Privacy |
| 12 | `api/app/templates/base.html` | edit | Удалить `<style>`, заменить на `<link>` |
| 13 | `api/app/templates/landing.html` | edit | Удалить `<style>`, подключить landing.css |
| 14 | `api/app/templates/terms.html` | edit | Удалить `<style>`, подключить legal.css |
| 15 | `api/app/templates/privacy.html` | edit | Удалить `<style>`, подключить legal.css |
| 16 | `api/app/templates/knowledge.html` | edit | Удалить `<style>`, обновить классы |
| 17 | `api/app/templates/integrations_hub.html` | edit | Удалить `<style>`, обновить классы |
| 18 | `api/app/templates/agent_detail.html` | edit | Удалить `<style>`, обновить классы |
| 19 | `api/app/templates/inbox.html` | edit | Обновить ссылки на стили |
| 20 | `api/app/templates/login.html` | edit | Удалить `<style>`, обновить классы |
| 21 | `api/app/templates/settings_*.html` | edit | Мелкие правки |
| 22 | `api/app/templates/agents_list.html` | edit | Мелкие правки |
| 23 | `api/app/templates/dashboard.html` | edit | Мелкие правки |

---

## Быстрые победы (можно сделать в первую неделю)

1. Создать `tokens.css` — 30 минут, максимальный impact
2. Добавить `--shadow-sm` на карты — 10 минут, кардинально меняет восприятие
3. Убрать h2 uppercase — 15 минут, современнее
4. Добавить `:focus-visible` — 20 минут, доступность
5. Card hover lift (translateY + shadow) — 15 минут, премиум-чувство
6. Пустые состояния (простая версия) — 30 минут, убирает "голые" страницы
7. Modal scale+fade entrance — 10 минут
8. Унифицировать button border-radius — 5 минут

---

## Структура CSS после рефакторинга

```
static/css/
├── tokens.css              # CSS-переменные (единственный source of truth)
├── base.css                # Reset, body, typography, layout
├── components.css          # Cards, buttons, forms, tables, modals, pills, toasts
├── landing.css             # Landing page (ex-landing.html <style>)
├── legal.css               # Terms + privacy
└── pages/
    ├── knowledge.css       # Knowledge base page
    ├── integrations.css    # Integrations hub
    ├── agent.css           # Agent detail
    ├── inbox.css           # Chat interface
    ├── login.css           # Auth page
    └── settings.css        # All settings pages
```
