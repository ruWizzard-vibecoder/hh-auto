# hh-auto — Автоматизация поиска работы на hh.ru

Система автоматического поиска вакансий, AI-оценки релевантности, генерации сопроводительных писем и отправки откликов на hh.ru.

## Содержание

- [Архитектура](#архитектура)
- [Пайплайн](#пайплайн)
- [Стек технологий](#стек-технологий)
- [Структура проекта](#структура-проекта)
- [Модели данных](#модели-данных)
- [API-эндпоинты](#api-эндпоинты)
- [Сервисы](#сервисы)
- [Шаблоны UI](#шаблоны-ui)
- [Расписание задач](#расписание-задач)
- [Конфигурация](#конфигурация)
- [Деплой](#деплой)
- [Первый запуск](#первый-запуск)
- [Потоки данных](#потоки-данных)
- [Обработка ошибок](#обработка-ошибок)
- [Ограничения и особенности hh.ru](#ограничения-и-особенности-hhru)

---

## Архитектура

### Гибридный подход: API + Browser

hh.ru закрыл API для соискателей 15.12.2025. Поисковый API (`api.hh.ru/vacancies`) остался публичным. Система использует два канала:

| Действие | Способ | Авторизация |
|----------|--------|-------------|
| Поиск вакансий | Публичный API | Нет |
| Получение деталей вакансии | Публичный API | Нет |
| Отправка откликов | Playwright (Chromium) | Да |
| Проверка статусов | Playwright (парсинг) | Да |
| Поднятие резюме | Playwright (клик) | Да |

### Двухуровневая AI-оценка

1. **Быстрая оценка (fast_score)** — эвристики по заголовку, навыкам, опыту (~10мс). Отсеивает нерелевантные вакансии (score < 0.3)
2. **AI-оценка (ai_score)** — Claude Haiku сравнивает полное описание вакансии с резюме (~2-5с). Возвращает score 0.0–1.0, обоснование, совпавшие/недостающие навыки

### Workflow с человеческим контролем

```
Вакансия найдена → Быстрая оценка → AI-оценка → Генерация письма
    → [ЧЕЛОВЕК: одобрить/редактировать/отклонить] → Отправка отклика → Мониторинг статуса
```

Письма НЕ отправляются автоматически — требуется одобрение в UI.

---

## Пайплайн

### 1. Поиск (Search Cycle)

```
SearchProfile (DB)
  → hh_client.search_all_pages() [публичный API, до 3 страниц × 100 вакансий]
    → Дедупликация (фильтр известных hh_id)
      → Фильтр по правилам компаний (blacklist/whitelist)
        → fast_score() [эвристики]
          → < 0.3: skip
          → >= 0.3: fetch full → ai_score() [Claude Haiku]
            → >= min_relevance_score: generate_cover_letter() [Claude Sonnet]
              → Сохранение: Vacancy (queued) + CoverLetter (pending)
```

### 2. Отклики (Apply Cycle)

```
CoverLetter (status=approved/edited)
  → Проверка дневного лимита (max 50)
    → browser.apply_to_vacancy(url, message) [Playwright]
      → Создание Application (status=sent)
        → Обновление CoverLetter.status=sent, Vacancy.status=applied
```

### 3. Проверка статусов (Status Check)

```
browser.get_negotiations() [парсинг страницы переговоров]
  → Сопоставление с Application по vacancy hh_id
    → Маппинг русских статусов:
        "отклик" → sent
        "просмотрен" → viewed
        "приглашение" → invited
        "предложение" → offer
        "отказ" → declined
```

### 4. Поднятие резюме (Resume Touch)

```
Активные SearchProfile → resume_id
  → browser.touch_resume(url) [клик "Поднять в поиске"]
```

### 5. Проверка архивности (Archive Check)

```
Vacancy (status=scored/queued)
  → hh_client.get_vacancy(hh_id) [публичный API]
    → 404: Vacancy.status = "archived", pending CoverLetters → "rejected"
    → 200: вакансия активна, без изменений
```

Запуск: автоматически каждые 12 часов + вручную из Настроек.

### 6. Дневная сводка (Daily Summary)

```
Агрегация за день: новые вакансии, отклики, ответы
  → Claude Sonnet: генерация отчёта (Markdown)
    → Сохранение DailySummary + отправка в Telegram
```

---

## Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Backend | FastAPI + Uvicorn (async) |
| Frontend | Jinja2 + HTMX 2.0 + PicoCSS |
| AI | OpenRouter → Claude Sonnet 4.5 (письма), Claude Haiku 4.5 (оценка) |
| Browser | Playwright (Chromium headless) |
| База данных | PostgreSQL 16 + SQLAlchemy 2.0 (async) |
| Планировщик | APScheduler 3.x |
| Уведомления | Telegram Bot API (aiogram) |
| HTTP-клиент | httpx + tenacity (retry) |
| Контейнеризация | Docker + Docker Compose |

---

## Структура проекта

```
hh-auto/
├── src/
│   ├── main.py                          # FastAPI app, lifespan (DB + scheduler)
│   ├── config.py                        # Pydantic Settings (env_prefix=HH_AUTO_)
│   ├── database.py                      # SQLAlchemy async engine + session
│   │
│   ├── api/                             # FastAPI роутеры
│   │   ├── dashboard.py                 # HTML-страницы (Jinja2 templates)
│   │   ├── auth.py                      # POST /auth/login, GET /auth/status
│   │   ├── cover_letters.py             # Одобрение/редактирование/отклонение писем
│   │   ├── settings_api.py              # CRUD поисковых профилей и правил
│   │   └── pipeline_api.py              # Ручной запуск циклов + статус
│   │
│   ├── models/                          # SQLAlchemy ORM модели
│   │   ├── vacancy.py                   # Вакансия с оценкой
│   │   ├── application.py               # Отправленный отклик
│   │   ├── cover_letter.py              # Сопроводительное письмо
│   │   ├── search_profile.py            # Параметры поиска
│   │   ├── company_rule.py              # Правила (blacklist/whitelist)
│   │   ├── resume.py                    # Резюме кандидата
│   │   ├── event_log.py                 # Лог событий
│   │   ├── daily_summary.py             # Дневная сводка
│   │   └── setting.py                   # Key-value настройки
│   │
│   ├── services/                        # Бизнес-логика
│   │   ├── hh_client.py                 # HTTP-клиент публичного API hh.ru
│   │   ├── hh_browser.py                # Playwright: логин, отклик, переговоры
│   │   ├── hh_auth.py                   # Управление авторизацией
│   │   ├── ai_client.py                 # OpenRouter обёртка (OpenAI SDK)
│   │   ├── vacancy_scorer.py            # fast_score + ai_score
│   │   ├── cover_letter_generator.py    # Генерация писем (Claude Sonnet)
│   │   ├── pipeline.py                  # Оркестрация: search → score → apply
│   │   ├── scheduler.py                 # APScheduler: расписание задач
│   │   ├── daily_summary.py             # AI-генерация дневных отчётов
│   │   └── telegram_bot.py              # Telegram-уведомления
│   │
│   └── templates/                       # Jinja2 HTML (все на русском)
│       ├── base.html                    # Лейаут: навигация, PicoCSS, HTMX
│       ├── dashboard.html               # Главная: статистика, воронка
│       ├── cover_letters.html           # Письма: просмотр/одобрение
│       ├── vacancies.html               # Вакансии: таблица с оценками
│       ├── applications.html            # Отклики: статусы
│       ├── settings.html                # Настройки: профили, правила
│       ├── summaries.html               # Дневные сводки
│       └── analytics.html               # Аналитика
│
├── data/
│   ├── resume_avanov_2026.md            # Резюме кандидата (контекст для AI)
│   └── browser_state/                   # Playwright state (persistent)
│       └── state.json
│
├── alembic/                             # Миграции БД
│   ├── env.py
│   └── versions/                        # (пока пусто — таблицы через create_all)
│
├── tests/                               # Тесты (TODO)
├── logs/                                # Логи runtime
├── Dockerfile                           # Python 3.12-slim + Chromium
├── docker-compose.yml                   # app + postgres
├── requirements.txt                     # Зависимости
├── alembic.ini                          # Конфиг миграций
└── .env.example                         # Шаблон переменных окружения
```

---

## Модели данных

### Vacancy — Вакансия

Обнаруженная вакансия с метаданными оценки.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int, PK | Внутренний ID |
| `hh_id` | str, unique | ID вакансии на hh.ru |
| `title` | str | Название |
| `company_name` | str | Компания |
| `company_id` | str | ID компании на hh.ru |
| `area_name` | str | Город/регион |
| `salary_from`, `salary_to` | int | Зарплатная вилка |
| `salary_currency` | str | Валюта (RUR, USD, EUR) |
| `experience` | str | Требуемый опыт (noExperience, between1And3, ...) |
| `schedule` | str | График (remote, fullDay, flexible) |
| `description` | text | Полное описание (HTML) |
| `key_skills` | JSONB | Список ключевых навыков |
| `relevance_score` | float | AI-оценка 0.0–1.0 |
| `score_reasoning` | str | Обоснование оценки |
| `matched_skills` | JSONB | Совпавшие навыки |
| `missing_skills` | JSONB | Недостающие навыки |
| `employment` | str | Тип занятости (full, part, project, probation) |
| `status` | str | discovered → scored → queued → applied / skipped / archived |
| `search_profile_id` | int | Профиль, по которому найдена |
| `url` | str | Ссылка на hh.ru |
| `response_letter_required` | bool | Требуется ли письмо |
| `discovered_at` | datetime | Когда найдена |

**Связи:** `cover_letters` (1:N), `applications` (1:N)

### CoverLetter — Сопроводительное письмо

AI-сгенерированное письмо, ожидающее проверки.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int, PK | |
| `vacancy_id` | int, FK | Для какой вакансии |
| `resume_id` | str | Какое резюме приложить |
| `generated_text` | text | Исходный AI-текст |
| `edited_text` | text | Отредактированный текст (если было) |
| `generation_prompt` | text | Промпт (обрезан до 5000 символов) |
| `model_used` | str | Модель (anthropic/claude-sonnet-4.5) |
| `status` | str | pending → approved/edited → sent / rejected |
| `rejection_reason` | str | Причина отклонения |
| `generated_at` | datetime | Когда сгенерировано |
| `reviewed_at` | datetime | Когда проверено |
| `sent_at` | datetime | Когда отправлено |

### Application — Отклик

Отправленный отклик и его статус.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int, PK | |
| `vacancy_id` | int, FK | Вакансия |
| `cover_letter_id` | int, FK | Письмо |
| `resume_id` | str | ID резюме на hh.ru |
| `status` | str | sent → viewed → invited / declined / offer |
| `hh_status` | str | Сырой статус с hh.ru |
| `applied_via` | str | "browser" |
| `applied_at` | datetime | Когда отправлен |
| `last_status_check` | datetime | Последняя проверка |

**Уникальность:** (vacancy_id, resume_id)

### SearchProfile — Поисковый профиль

Параметры поиска вакансий. Поиск ведётся по всей России (area_id=NULL), а предпочтения по регионам реализованы через scoring по часовым поясам.

| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `name` | str | — | Название профиля |
| `is_active` | bool | true | Активен ли |
| `search_text` | str | — | Поисковый запрос |
| `area_id` | int | — | Регион (1=Москва, 2=СПб) |
| `experience` | str | — | noExperience, between1And3, between3And6, moreThan6 |
| `employment` | str | — | full, part, project, probation |
| `schedule` | str | — | remote, fullDay, flexible |
| `salary_from` | int | — | Минимальная зарплата |
| `min_relevance_score` | float | 0.5 | Порог для генерации письма |
| `resume_id` | str | — | ID/URL резюме на hh.ru |
| `order_by` | str | publication_time | Сортировка |

### CompanyRule — Правило компании

| Поле | Описание |
|------|----------|
| `rule_type` | "blacklist" или "whitelist" |
| `match_type` | "company_name", "company_id", "keyword_in_title" |
| `match_value` | Значение для сравнения |
| `reason` | Причина (опционально) |

### DailySummary — Дневная сводка

| Поле | Описание |
|------|----------|
| `summary_date` | Дата (уникальная) |
| `vacancies_discovered`, `applications_sent`, ... | Счётчики за день |
| `summary_text` | AI-сгенерированный Markdown-отчёт |
| `top_vacancies` | JSONB: топ-5 вакансий |
| `interview_prep` | JSONB: советы к собеседованиям |
| `insights` | Тренды рынка |

### EventLog — Лог событий

Аудит-лог всех действий системы: `search_cycle_complete`, `application_sent`, `status_changed`, `search_error`, `application_failed`.

---

## API-эндпоинты

### HTML-страницы (dashboard.py)

| Маршрут | Описание |
|---------|----------|
| `GET /` | Главная: статистика, воронка, последние события |
| `GET /cover-letters` | Письма: просмотр/одобрение (фильтр по статусу) |
| `GET /vacancies` | Вакансии: таблица с оценками (пагинация, фильтр) |
| `GET /applications` | Отклики: отправленные, статусы |
| `GET /settings` | Настройки: логин, профили, правила |
| `GET /analytics` | Аналитика: метрики |
| `GET /summaries` | Дневные сводки |

### Авторизация (auth.py)

| Маршрут | Описание |
|---------|----------|
| `POST /auth/login` | Логин на hh.ru (Form: email, password). Редирект 303 |
| `GET /auth/status` | `{"authenticated": true/false}` |

### Письма (cover_letters.py)

| Маршрут | Описание |
|---------|----------|
| `POST /api/cover-letters/{id}/approve` | Одобрить письмо |
| `POST /api/cover-letters/{id}/edit` | Отредактировать + одобрить (Form: edited_text) |
| `POST /api/cover-letters/{id}/reject` | Отклонить (Form: reason) |

Возвращают HTML-фрагмент для HTMX swap.

### Настройки (settings_api.py)

| Маршрут | Описание |
|---------|----------|
| `POST /api/settings/profiles` | Создать поисковый профиль |
| `PUT /api/settings/profiles/{id}` | Обновить профиль |
| `POST /api/settings/rules` | Добавить правило компании |
| `DELETE /api/settings/rules/{id}` | Деактивировать правило |

### Пайплайн (pipeline_api.py)

| Маршрут | Описание |
|---------|----------|
| `POST /api/pipeline/search` | Запустить цикл поиска (async) |
| `POST /api/pipeline/apply` | Запустить цикл откликов (async) |
| `POST /api/pipeline/status-check` | Проверить статусы (async) |
| `POST /api/pipeline/archive-check` | Проверить архивность вакансий (async) |
| `POST /api/summaries/generate` | Сгенерировать сводку (async) |
| `GET /api/status` | Статус сервиса (для футера UI) |
| `GET /api/events/recent` | Последние 20 событий (HTML) |
| `POST /api/vacancies/{id}/blacklist` | Добавить компанию в чёрный список |
| `POST /api/vacancies/{id}/generate-letter` | Сгенерировать письмо вручную |
| `GET /health` | Healthcheck |

---

## Сервисы

### hh_client.py — Публичный API hh.ru

Асинхронный HTTP-клиент для `api.hh.ru`.

- **Rate limiting:** 5 одновременных запросов, 250мс между запросами
- **Retry:** 3 попытки с exponential backoff (только сетевые ошибки)

| Метод | Описание |
|-------|----------|
| `search_vacancies(text, area, experience, schedule, ...)` | Поиск (1 страница, до 100) |
| `search_all_pages(max_pages=5, **kwargs)` | Поиск по нескольким страницам |
| `get_vacancy(vacancy_id)` | Полные данные вакансии |

**Dataclass'ы:** `VacancyShort`, `VacancyFull` (+ description), `HHApiError`

### hh_browser.py — Playwright (Singleton)

Headless Chromium для авторизованных действий. State: `/app/data/browser_state/state.json`.

| Метод | Описание |
|-------|----------|
| `login(email, password)` | 6-шаговый логин на hh.ru |
| `apply_to_vacancy(url, message)` | Отправка отклика с письмом |
| `get_negotiations()` | Парсинг страницы переговоров → `list[BrowserNegotiation]` |
| `touch_resume(url)` | Поднятие резюме в поиске |
| `is_logged_in()` | Проверка наличия state.json |

**Singleton:** `get_browser()` — единственный экземпляр.

### ai_client.py — OpenRouter

Обёртка AsyncOpenAI для OpenRouter (`openrouter.ai/api/v1`).

| Функция | Описание |
|---------|----------|
| `get_client()` | Singleton AsyncOpenAI |
| `ai_complete(prompt, system, model, max_tokens)` | Запрос к LLM → `AIResponse(text, tokens)` |

**Модели по умолчанию:**
- Письма/сводки: `anthropic/claude-sonnet-4.5`
- Оценка: `anthropic/claude-haiku-4.5`

### vacancy_scorer.py — Двухуровневая оценка

**fast_score()** — эвристики (~10мс):
- Тирированные ключевые слова в заголовке (разный бонус по тирам):
  - Tier 1 (+0.35): ai engineer, automation engineer, no-code, low-code, n8n, ai solutions, vibe cod
  - Tier 2 (+0.25): ai product, ai consultant, llm engineer, prompt engineer, data engineer, mlops
  - Exact (+0.20): ai, ml, llm (с проверкой границ слова, не сработает на "email")
  - Tier 3 (+0.10): python developer, backend developer, devops, разработчик (минимальный бонус)
- Негативные ключевые слова → score = 0.0
- Совпадение навыков (AI, Dev, DevOps, Automation) (+0.1 за навык, до 0.4)
- Бонус за удалёнку (+0.1)
- Бонус за частичную занятость/подработку (+0.15) — ключевые слова: частичная занятость, подработка, проектная работа, freelance, контракт и т.д.
- Региональный скоринг по часовым поясам:
  - Предпочтительные MSK (+0.05): Москва, СПб, Казань, Краснодар, Минск, Тбилиси...
  - Ближайшие UTC+4-5 (0.00): Екатеринбург, Самара, Уфа, Астана, Алматы...
  - Средние UTC+6-7 (-0.05): Новосибирск, Красноярск, Омск, Томск...
  - Дальние UTC+8+ (-0.15): Иркутск, Хабаровск, Владивосток...

**ai_score()** — Claude Haiku (~2-5с):
- Полное описание + резюме → JSON
- Контекст: кандидат ищет подработку/частичную занятость, не полную
- Целевые роли по тирам (Tier 1-3) включены в промпт
- Возвращает: score, reasoning, matched_skills, missing_skills, recommended_emphasis
- Fallback при ошибке: score=0.5
- Обработка обрезанного JSON: regex-извлечение score

### cover_letter_generator.py — Генерация писем

Claude Sonnet: русский язык, 150-250 слов, конкретные примеры из резюме, учёт рекомендаций AI-оценки. Контекст подработки: для part-time/project вакансий подчёркивает гибкость, для full-time — не упоминает.

### pipeline.py — Оркестратор

`Pipeline(db, hh_client, hh_browser)`:

| Метод | Описание |
|-------|----------|
| `run_search_cycle()` | Поиск → оценка → генерация |
| `run_apply_cycle()` | Одобренные письма → Playwright |
| `run_status_check()` | Переговоры → обновление статусов |
| `run_resume_touch()` | Поднятие резюме |
| `run_archive_check()` | Проверка актуальности вакансий (404 = архив) |

### scheduler.py — Планировщик

APScheduler с 5 задачами. Каждая создаёт Pipeline со своей DB-сессией.

### daily_summary.py — Дневные сводки

Агрегация + Claude Sonnet → Markdown-отчёт + Telegram.

### telegram_bot.py — Уведомления

`notify_new_match()`, `notify_status_change()`, `notify_search_complete()`, `send_message()`.

---

## Шаблоны UI

PicoCSS + HTMX. Все на русском.

| Шаблон | Описание |
|--------|----------|
| `base.html` | Навбар с бейджем pending, футер со live-статусом |
| `dashboard.html` | 6 метрик, таблица воронки, HTMX-обновление событий |
| `cover_letters.html` | Табы по статусам, фильтры по занятости, карточки с навыками и бейджами: одобрить/редактировать/отклонить |
| `vacancies.html` | Таблица с оценками, фильтры по занятости (Частичная/Проектная/Полная), колонка "Детали" (matched/missing skills, бейджи занятости), вкладка "Архив" |
| `applications.html` | Статусы с бейджами |
| `settings.html` | Логин, CRUD профилей, CRUD правил |
| `summaries.html` | AI-отчёты по дням |
| `analytics.html` | Метрики (агрегации TODO) |

---

## Расписание задач

| Задача | Интервал | Требует логин | Описание |
|--------|----------|---------------|----------|
| Поиск вакансий | 4 часа | Нет | Публичный API |
| Отправка откликов | 30 минут | Да | Одобренные письма → Playwright |
| Проверка статусов | 6 часов | Да | Парсинг переговоров |
| Поднятие резюме | 4 часа | Да | Клик "Поднять в поиске" |
| Проверка архивности | 12 часов | Нет | API-проверка (404 = архив), reject pending писем |
| Дневная сводка | 22:00 | Нет | AI-отчёт + Telegram |

Задачи с `Да` вызывают `ensure_logged_in()` → пропуск если невозможно.

---

## Конфигурация

Все параметры из env с префиксом `HH_AUTO_`. Определены в `src/config.py`.

### Обязательные

| Переменная | Описание |
|------------|----------|
| `HH_AUTO_DATABASE_URL` | PostgreSQL connection string |
| `HH_AUTO_HH_EMAIL` | Email hh.ru |
| `HH_AUTO_HH_PASSWORD` | Пароль hh.ru |
| `HH_AUTO_OPENROUTER_API_KEY` | API-ключ OpenRouter |

### Опциональные

| Переменная | По умолчанию | Описание |
|------------|-------------|----------|
| `HH_AUTO_AI_MODEL` | `anthropic/claude-sonnet-4.5` | Модель для писем |
| `HH_AUTO_SCORING_MODEL` | `anthropic/claude-haiku-4.5` | Модель для оценки |
| `HH_AUTO_TELEGRAM_BOT_TOKEN` | — | Telegram бот |
| `HH_AUTO_TELEGRAM_CHAT_ID` | — | Chat ID |
| `HH_AUTO_SEARCH_INTERVAL_HOURS` | 4 | Интервал поиска |
| `HH_AUTO_APPLY_INTERVAL_MINUTES` | 30 | Интервал откликов |
| `HH_AUTO_STATUS_CHECK_INTERVAL_HOURS` | 6 | Интервал проверки |
| `HH_AUTO_MAX_APPLICATIONS_PER_DAY` | 50 | Лимит откликов/день |

### .env для Docker Compose

```env
POSTGRES_PASSWORD=your_pg_password
HH_EMAIL=your@email.com
HH_PASSWORD=your_password
OPENROUTER_API_KEY=sk-or-v1-...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

Docker Compose пробрасывает их с префиксом `HH_AUTO_`.

---

## Деплой

### Docker Compose

Два контейнера: `hh-auto` (FastAPI + Chromium) и `hh-auto-postgres` (PG16).

```bash
docker compose up -d --build
```

### Сети

- `default` — app ↔ postgres
- `claude-code-nas_claude-network` — xray-client прокси для OpenRouter (обход блокировки из России)

### Volumes

| Хост | Контейнер | Описание |
|------|-----------|----------|
| `./data` | `/app/data` | Резюме + browser state |
| `./logs` | `/app/logs` | Логи |
| `postgres_data` | `/var/lib/postgresql/data` | PostgreSQL |

### Healthcheck

`curl -f http://localhost:8100/health` каждые 30с.

---

## Первый запуск

1. Создать `.env` (см. выше)
2. Положить резюме в `data/resume_avanov_2026.md`
3. `docker compose up -d --build`
4. Открыть `http://<host>:8100/settings`
5. Ввести email/пароль hh.ru → «Войти на hh.ru»
6. Создать поисковый профиль:
   - Название: "Python разработчик, СПб"
   - Поисковый запрос: "Python разработчик"
   - Регион: 2 (Санкт-Петербург)
   - Мин. оценка: 0.5
   - Опыт: 3-6 лет
   - График: Удалённая
7. «Запустить поиск» в блоке "Управление"
8. Ожидание: 30-60с поиск, до 15 минут AI-обработка
9. Страница «Письма» → одобрить/отредактировать
10. Одобренные письма отправятся автоматически (каждые 30 минут)

### Регионы hh.ru (area_id)

| ID | Город |
|----|-------|
| 1 | Москва |
| 2 | Санкт-Петербург |
| 113 | Россия (вся) |

---

## Потоки данных

### Жизненный цикл вакансии

```
hh.ru API                                 UI
  ↓                                        ↑
search_vacancies()                   /vacancies
  ↓                                        ↑
fast_score()                         status=skipped (< 0.3)
  ↓ >= 0.3                                ↑
ai_score() [Haiku]                   status=scored (ниже порога)
  ↓ >= threshold                           ↑
generate_cover_letter() [Sonnet]     status=queued ←── archive_check() → status=archived
  ↓                                        ↓
CoverLetter (pending) ─────────→ /cover-letters
                                           ↓
                          [ЧЕЛОВЕК: одобрить/редактировать]
                                           ↓
browser.apply_to_vacancy()         /applications
  ↓                                        ↑
Application (sent) ──────────→ status=sent/viewed/invited/declined
```

### Стоимость AI-вызовов (на вакансию)

| Вызов | Модель | Input | Output |
|-------|--------|-------|--------|
| ai_score | Haiku 4.5 | ~500 токенов | ~200-400 токенов |
| cover_letter | Sonnet 4.5 | ~2500 токенов | ~500 токенов |

---

## Обработка ошибок

| Ситуация | Поведение |
|----------|----------|
| hh.ru API 429 (rate limit) | Retry с exponential backoff (3 попытки) |
| hh.ru API недоступен | Retry, затем пропуск вакансии |
| OpenRouter ошибка | AI score fallback = 0.5, письмо не генерируется |
| JSON от AI обрезан | Извлечение score через regex |
| hh.ru API 404 (при archive check) | Вакансия → "archived", pending письма → "rejected" |
| Browser login failed | Цикл откликов пропускается |
| Playwright crash | Ошибка логируется, цикл пропускается |
| Telegram недоступен | Не блокирует основной процесс |

---

## Ограничения и особенности hh.ru

### API

- Поисковый API — публичный, ~7 req/sec, макс 2000 результатов
- API соискателя — **закрыт с 15.12.2025**

### Логин через браузер (февраль 2026)

6-шаговый процесс:

1. Открыть `hh.ru/account/login`
2. Кликнуть «Войти» (`[data-qa="submit-button"]`)
3. Кликнуть label «Почта» (`force=True` — overlay)
4. Заполнить email (`[data-qa="applicant-login-input-email"]`)
5. Кликнуть «Войти с паролем» (`[data-qa="expand-login-by-password"]`, `force=True`)
6. Заполнить пароль → submit → ожидание навигации

**Важно:**
- Radio-кнопки перекрыты overlay → `force=True`
- Редирект после логина: `hh.ru/` (НЕ `/applicant/`)
- State: `/app/data/browser_state/state.json`

### Отклик через браузер

1. Открыть вакансию → проверить «Вы уже откликнулись»
2. Кликнуть `[data-qa="vacancy-response-link-top"]`
3. Заполнить textarea → submit → ждать «Отклик отправлен»

### Статусы переговоров

Элементы `[data-qa="negotiations-list-item"]` на `hh.ru/applicant/negotiations`:
- отклик → sent
- просмотрен → viewed
- приглашение → invited
- отказ → declined
- предложение → offer
