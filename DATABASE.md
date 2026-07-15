# Схема базы данных ChatList

База данных: **SQLite**  
Файл по умолчанию: `chatlist.db` (путь можно хранить в настройках)

---

## Обзор таблиц

| Таблица    | Назначение                                      |
|------------|-------------------------------------------------|
| `prompts`  | Сохранённые промты пользователя                 |
| `models`   | Нейросети и параметры подключения к API         |
| `results`  | Сохранённые ответы моделей                      |
| `settings` | Настройки программы (ключ–значение)             |

---

## Таблица `prompts`

Хранит запросы пользователя для повторного использования.

| Поле         | Тип          | Ограничения              | Описание                        |
|--------------|--------------|--------------------------|---------------------------------|
| `id`         | INTEGER      | PRIMARY KEY AUTOINCREMENT| Уникальный идентификатор        |
| `created_at` | TEXT         | NOT NULL                 | Дата и время создания (ISO 8601)|
| `prompt`     | TEXT         | NOT NULL                 | Текст промта                    |
| `tags`       | TEXT         | NULL                     | Теги через запятую, напр. `code,test` |

**Индексы:**
- `idx_prompts_created_at` — сортировка по дате;
- `idx_prompts_tags` — опционально, для поиска по тегам.

---

## Таблица `models`

Список нейросетей. API-ключи **не хранятся** в БД — только имя переменной окружения.

| Поле        | Тип          | Ограничения              | Описание                                      |
|-------------|--------------|--------------------------|-----------------------------------------------|
| `id`        | INTEGER      | PRIMARY KEY AUTOINCREMENT| Уникальный идентификатор                      |
| `name`      | TEXT         | NOT NULL UNIQUE          | Отображаемое имя модели                       |
| `api_url`   | TEXT         | NOT NULL                 | URL endpoint API                              |
| `api_id`    | TEXT         | NOT NULL                 | Имя переменной в `.env`, напр. `OPENAI_API_KEY` |
| `is_active` | INTEGER      | NOT NULL DEFAULT 1       | 1 — участвует в отправке, 0 — отключена       |
| `model_type`| TEXT         | NULL                     | Тип API: `openai`, `deepseek`, `groq` и т.д.  |

**Индексы:**
- `idx_models_is_active` — быстрый выбор активных моделей.

**Пример записи:**

| name       | api_url                              | api_id           | is_active |
|------------|--------------------------------------|------------------|-----------|
| GPT-4o     | https://api.openai.com/v1/chat/completions | OPENAI_API_KEY | 1         |

---

## Таблица `results`

Постоянное хранение ответов, отмеченных пользователем для сохранения.

| Поле          | Тип          | Ограничения              | Описание                              |
|---------------|--------------|--------------------------|---------------------------------------|
| `id`          | INTEGER      | PRIMARY KEY AUTOINCREMENT| Уникальный идентификатор              |
| `created_at`  | TEXT         | NOT NULL                 | Дата и время сохранения               |
| `prompt_id`   | INTEGER      | NULL, FK → `prompts.id`  | Ссылка на промт (если был сохранён)   |
| `model_id`    | INTEGER      | NOT NULL, FK → `models.id` | Ссылка на модель                    |
| `prompt_text` | TEXT         | NOT NULL                 | Копия текста промта на момент запроса |
| `response`    | TEXT         | NOT NULL                 | Текст ответа модели                   |

**Связи:**
- `prompt_id` — SET NULL при удалении промта (история ответов сохраняется);
- `model_id` — RESTRICT при удалении модели (нельзя удалить модель с результатами).

**Индексы:**
- `idx_results_created_at` — сортировка по дате;
- `idx_results_prompt_id` — фильтр по промту;
- `idx_results_model_id` — фильтр по модели.

---

## Таблица `settings`

Настройки программы в формате ключ–значение.

| Поле   | Тип  | Ограничения       | Описание              |
|--------|------|-------------------|-----------------------|
| `key`  | TEXT | PRIMARY KEY       | Имя настройки         |
| `value`| TEXT | NULL              | Значение настройки    |

**Примеры настроек:**

| key              | value              |
|------------------|--------------------|
| `db_path`        | `chatlist.db`      |
| `request_timeout`| `60`               |
| `theme`          | `light`            |
| `window_width`   | `900`              |
| `window_height`  | `600`              |

---

## Временная таблица результатов (не в SQLite)

Используется только в памяти приложения между отправкой промта и сохранением.

| Поле         | Тип    | Описание                          |
|--------------|--------|-----------------------------------|
| `model_name` | TEXT   | Название модели                   |
| `response`   | TEXT   | Текст ответа или сообщение об ошибке |
| `selected`   | BOOL   | Отмечен ли чекбоксом пользователем |
| `model_id`   | INT    | ID модели (для записи в `results`) |

При новом запросе список полностью очищается и заполняется заново.

---

## Диаграмма связей

```
prompts (1) ──────< (N) results
                      │
models  (1) ──────< (N) results

settings — независимая таблица
```

---

## SQL инициализации

```sql
CREATE TABLE IF NOT EXISTS prompts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT    NOT NULL,
    prompt     TEXT    NOT NULL,
    tags       TEXT
);

CREATE TABLE IF NOT EXISTS models (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    api_url    TEXT    NOT NULL,
    api_id     TEXT    NOT NULL,
    is_active  INTEGER NOT NULL DEFAULT 1,
    model_type TEXT
);

CREATE TABLE IF NOT EXISTS results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    prompt_id   INTEGER,
    model_id    INTEGER NOT NULL,
    prompt_text TEXT    NOT NULL,
    response    TEXT    NOT NULL,
    FOREIGN KEY (prompt_id) REFERENCES prompts(id) ON DELETE SET NULL,
    FOREIGN KEY (model_id)  REFERENCES models(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_prompts_created_at ON prompts(created_at);
CREATE INDEX IF NOT EXISTS idx_models_is_active ON models(is_active);
CREATE INDEX IF NOT EXISTS idx_results_created_at ON results(created_at);
CREATE INDEX IF NOT EXISTS idx_results_prompt_id ON results(prompt_id);
CREATE INDEX IF NOT EXISTS idx_results_model_id ON results(model_id);
```

---

## Примечания

- Даты хранятся в формате ISO 8601: `2026-07-15T12:00:00`.
- API-ключи загружаются из `.env` по полю `models.api_id`.
- Временные результаты в SQLite не пишутся — только в оперативной памяти GUI.
- Поле `model_type` опционально и нужно для поддержки разных форматов API (см. PROJECT.md, раздел 6).
