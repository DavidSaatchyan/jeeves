# OpenFlo — Гайд по использованию

> Как использовать OpenFlo для разработки и управления проектами

---

## Что это и зачем

OpenFlo — это набор **агентов, инструментов и памяти** для OpenCode. Он позволяет:

- **Не терять контекст** — память между сессиями (SQLite + векторный поиск)
- **Делить работу** — 19 специализированных агентов вместо одного универсального
- **Планировать** — декомпозировать задачи, отслеживать прогресс
- **Координироваться** — передавать задачи между проектами (federation)

Всё бесплатно через OpenCode Zen (DeepSeek V4 Flash + Big Pickle).

### 16 Навыков (Skills) высокого уровня

Каждый навык — это SKILL.md (300-400 строк для доменных, 40-120 для системных) с приоритетными категориями, Do/Don't таблицами, код-примерами и чеклистами. У ux-designer дополнительно 6 JSON-баз (105KB) и поисковый движок.

**Доменные (300-400 строк):**
- `ux-designer` — 49 стилей, 43 палитры, 45 шрифтов, 51 продукт, 80+ UX правил
- `frontend-developer` — React/Vue/Angular/Svelte матрица, 12 категорий
- `backend-developer` — API, БД, кеш, очереди, 12 категорий
- `security-engineer` — OWASP Top 10, AES-256-GCM, ABAC
- `test-master` — TDD, property-based, MSW, CI/CD
- `devops-engineer` — Docker, K8s, Terraform, incident response
- `architecture-designer` — CQRS/ES, Saga, ADR, canary deploy

**Системные (40-120 строк):**
- swarm, memory, self-learning, goal-planning, consensus, federation, workers, observability, web-ui

**Поисковый движок** (для ux-designer):
```bash
node .opencode/skills/shared/search.js "fintech crypto" --design-system -p "MyApp"
node .opencode/skills/shared/search.js "glassmorphism" --domain styles
node .opencode/skills/shared/search.js "form validation" --domain ux-rules
```

**CLI:**
```bash
node cli/openflo-skill.js list          # список навыков
node cli/openflo-skill.js init .        # установка в проект
```

---

## 1. Установка в новый проект

**Рекомендуемый способ** — скрипт установки. Он сделает merge, не сломав существующий проект:

```powershell
.\scripts\install.ps1 C:\Users\me\my-project
```

Что будет установлено:

| Компонент | Что внутри | Для чего |
|-----------|-----------|----------|
| `opencode.json` | 19 агентов, MCP сервер, 2 плагина | Конфигурация OpenCode |
| `AGENTS.md` | Правила работы, workflow, агенты | Инструкции для всех агентов |
| `.opencode/skills/` | 16 навыков (SKILL.md + JSON базы) | Доменные знания для агентов |
| `.opencode/plugins/` | openflo-core.ts + aidefence.ts | Авто-память + защита |
| `mcp/openflo-mcp/` | 24 MCP тула, SQLite, векторный поиск | Память, graph, goals, federation |
| `mcp/openflo-federation/` | ed25519, trust, WebSocket transport | Связь между проектами |
| `cli/` | CLI для управления навыками | `openflo-skill.js` |
| `web/` | HTML/CSS/JS дашборд | Визуальный мониторинг |
| `scripts/` | pre-commit + post-commit хуки | Git-интеграция |

Скрипт делает:
- **Merge** `opencode.json` — твои агенты сохраняются, OpenFlo-агенты добавляются
- **Merge** `.opencode/` — файлы из OpenFlo добавляются, твои не трогаются
- **Merge** `AGENTS.md` — твой текст в начале, правила OpenFlo в конце
- **npm install** в `mcp/openflo-mcp/` — зависимости MCP сервера

### Установка вручную (если скрипт не запускается)

```powershell
# PowerShell
Copy-Item -Path C:\openflo\opencode.json -Destination .\ -Force
Copy-Item -Path C:\openflo\AGENTS.md -Destination .\ -Force
Copy-Item -Path C:\openflo\.opencode -Destination .\ -Recurse -Force
Copy-Item -Path C:\openflo\mcp -Destination .\ -Recurse -Force
Copy-Item -Path C:\openflo\cli -Destination .\ -Recurse -Force
Copy-Item -Path C:\openflo\web -Destination .\ -Recurse -Force
Copy-Item -Path C:\openflo\scripts -Destination .\ -Recurse -Force
cd mcp\openflo-mcp
npm install --no-audit --no-fund
cd ..\..
opencode
```

OpenCode сам подхватит `opencode.json` и запустит MCP сервер.

---

## 1.5 Проверка что всё работает (5 шагов)

После `npm install` и запуска OpenCode, напиши в чат по порядку:

**Шаг 1 — агенты:**
```
/agents list
```
→ Должен показать 19 агентов: swarm, architect, implementer, reviewer, tester...

**Шаг 2 — память:**
```
openflo_learn(key: "test:hello", content: "Привет, мир!", tags: ["test"])
```
→ Ответ: `Stored: "test:hello" (id: ...)`

**Шаг 3 — поиск в памяти:**
```
openflo_recall(tag: "test")
```
→ Должен найти запись из шага 2.

**Шаг 4 — статистика:**
```
openflo_stats()
```
→ Покажет `Total memories: 1 (или больше)`

**Шаг 5 — вызов агента:**
```
/agent researcher покажи файлы в корне проекта
```
→ Researcher должен ответить списком файлов.

**Если всё прошло без ошибок — OpenFlo работает.** Если ошибка — покажи её текст, я помогу.

---

## 2. Ежедневная работа

### 2.1 Начать сессию

```bash
opencode
```

По умолчанию запускается агент **swarm** — он решает, кого делегировать.

### 2.2 Основные команды

| Команда | Что делает | Когда использовать |
|---------|-----------|-------------------|
| `/agents list` | Показать всех агентов | Не знаете, кого выбрать |
| `/agents suggest <задача>` | AI рекомендует агента | Новая задача, неочевидный выбор |
| `/agent <имя> <задача>` | Запустить конкретного агента | Точно знаете, кто нужен |

### 2.3 Работа с памятью

OpenFlo автоматически запоминает всё, что вы делаете (через плагин `openflo-core.ts`). Но можно и вручную:

```
# Сохранить решение (чтобы не забыть через неделю)
openflo_learn(key: "billing:stripe-choice", content: "Выбрали Stripe, потому что...", tags: ["architecture", "billing"])

# Найти сохранённое
openflo_recall(query: "почему выбрали stripe")
openflo_recall(tag: "architecture", limit: 20)
openflo_recall(mode: "semantic", query: "payment processing decision")  # векторный поиск

# Семантический поиск (по смыслу, а не по словам)
openflo_recall(mode: "semantic", query: "как авторизовать пользователя")

# Посмотреть статистику памяти
openflo_stats()
```

Память сохраняется между сессиями и проектами (если настроен federation).

---

## 3. Когда какого агента звать

### Сложные задачи (DeepSeek V4 Flash)

| Ситуация | Агент | Пример запроса |
|----------|-------|---------------|
| Нужно спроектировать архитектуру | `architect` | "спроектируй модуль авторизации" |
| Написать код по плану | `implementer` | "реализуй UserRepository из плана" |
| Проверить код перед коммитом | `reviewer` | "проверь пул-реквест #12" |
| Написать тесты | `tester` | "напиши тесты для billing.ts" |
| Найти баг | `debugger` | "тест падает с таймаутом, разберись" |
| Проверить безопасность | `security` | "проверь зависимости на уязвимости" |
| Отрефакторить | `refactorer` | "убери дублирование в контроллерах" |

### Быстрые задачи (Big Pickle)

| Ситуация | Агент | Пример запроса |
|----------|-------|---------------|
| Разобраться в коде | `researcher` | "как работает WebSocket сервер?" |
| Написать документацию | `documenter` | "напиши README для модуля" |
| Настроить CI/CD | `devops` | "настрой GitHub Actions" |
| Оптимизировать | `perf` | "найди медленные запросы" |
| Обновить зависимости | `deps` | "обнови пакеты до последних" |
| Добавить переводы | `i18n` | "добавь русский язык" |
| Проверить лицензии | `legal` | "проверь лицензии зависимостей" |
| UX/доступность | `ux` | "проверь WCAG" |

---

## 4. Планирование и цели

### Создать план

```
openflo_goal_save(
  name: "add-payment",
  description: "Добавить модуль платежей",
  plan: {
    tasks: [
      { label: "Выбрать провайдера", priority: "P0", estimatedHours: 2 },
      { label: "Интегрировать API", priority: "P0", estimatedHours: 8, dependsOn: ["Выбрать провайдера"] },
      { label: "Написать тесты", priority: "P1", estimatedHours: 4, dependsOn: ["Интегрировать API"] },
    ]
  }
)
```

### Следить за прогрессом

```
# Статус по конкретной цели
openflo_goal_status(name: "add-payment")

# Адаптивное перепланирование (если что-то заблокировано)
openflo_goal_replan(name: "add-payment")
```

### Жизненный цикл цели

1. **Создали** — `openflo_goal_save`
2. **Работаете** — обновляете статус задач вручную
3. **Заблокировались** — `openflo_goal_replan` предложит альтернативы
4. **Завершили** — задачи автоматически отмечаются

---

## 5. Консенсус (когда нужно решить спорный вопрос)

```
# Начать голосование
openflo_consensus_vote(
  topic: "Выбор БД: PostgreSQL vs MySQL",
  options: ["postgres", "mysql"],
  votes: [
    { voter: "architect", option: "postgres", reasoning: "JSONB, GIN indexes" },
    { voter: "implementer", option: "postgres", reasoning: "уже используем" },
    { voter: "perf", option: "mysql", reasoning: "быстрее на чтение" },
  ]
)

# Посмотреть результат
openflo_consensus_tally(topic: "Выбор БД: PostgreSQL vs MySQL")
```

---

## 6. Federation: работа между проектами

Если у вас несколько проектов с OpenFlo, они могут обмениваться памятью и задачами.

```
# Посмотреть известные пиры
openflo_federation_peers()

# Отправить задачу в другой проект
openflo_federation_send(
  target: "a1b2c3d4e5f6g7h8",
  type: "task_request",
  payload: { goal: "портировать AuthModule в project-b" }
)

# Статус федерации
openflo_federation_status()
```

Federation работает через:
- **ed25519** ключи (каждый экземпляр имеет уникальный ID)
- **Trust scoring** (0.4×success + 0.2×uptime + 0.2×threat + 0.2×age)
- **WebSocket** (через `transport.js`, порт 4322)
- **Offline queue** (сообщения сохраняются, если пир недоступен)

---

## 7. Самообучение (SONA-light)

OpenFlo автоматически записывает траектории — какие инструменты вызывались, какие ошибки произошли. Это позволяет:

- Находить похожие проблемы через `openflo_patterns`
- Использовать ReasoningBank — сохранённые решения проблем
- Улучшать качество с каждой сессией

```
# Найти паттерн (похожие ситуации из прошлого)
openflo_patterns(query: "ошибка подключения к БД")

# Поиск в ReasoningBank (проблема → решение)
openflo_reasoning(query: "WebSocket disconnect")
```

---

## 8. Безопасность (AIDefence)

Плагин `aidefence.ts` автоматически:

- **Блокирует prompt injection** ("игнорируй предыдущие инструкции")
- **Сканирует PII** (ключи API, токены, email, кредитные карты)
- **Проверяет файлы** на вредоносный код

Всё в режиме `warn` (предупреждает, но не блокирует). Можно сменить на `block` в `opencode.json`:

```json
"aidefence": { "mode": "block" }
```

Явно проверить текст на PII:

```
openflo_pii_scan(text: "my api key is sk-xxx")
```

---

## 9. Web UI

OpenFlo включает веб-дашборд для визуального мониторинга:

```
# MCP сервер уже запущен, открыть в браузере:
open web/index.html
```

Или откройте `http://127.0.0.1:4321/health` — увидите статус сервера.

---

## 10. Быстрый старт (шпаргалка)

```powershell
# 1. Установить OpenFlo в проект
.\scripts\install.ps1 C:\путь\до\проекта

# 2. Запустить OpenCode
cd C:\путь\до\проекта
opencode

# 3. Проверить агентов
/agents list

# 4. Сохранить первую памятку
openflo_learn(key: "start", content: "Начали работу с OpenFlo", tags: ["onboarding"])

# 5. Создать первую цель
/agent goal "Создать план для авторизации"
openflo_goal_save(name: "auth", description: "Модуль авторизации", plan: {tasks: [...]

# 6. Начать работу
/agent implementer "реализуй JWT middleware"
```

---

## Сводка: что когда использовать

| Задача | Инструмент |
|--------|-----------|
| "С чего начать?" | `swarm` (агент по умолчанию) |
| "Забыл решение" | `openflo_recall` |
| "Нужен план" | `openflo_goal_save` + `/agent architect` |
| "Написать код" | `/agent implementer` |
| "Проверить код" | `/agent reviewer` |
| "Найти баг" | `/agent debugger` |
| "Упал тест" | `openflo_patterns` + `/agent debugger` |
| "Передать в другой проект" | `openflo_federation_send` |
| "Спорное решение" | `openflo_consensus_vote` |
| "Следить за прогрессом" | `openflo_goal_status` |
| "Посмотреть что происходит" | Web UI (`web/index.html`) |
