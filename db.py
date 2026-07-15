"""Доступ к SQLite для ChatList."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "chatlist.db"

SCHEMA_SQL = """
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
"""

DEFAULT_SETTINGS = {
    "db_path": DEFAULT_DB_PATH,
    "request_timeout": "60",
}

SEED_MODELS = [
    {
        "name": "GPT-4o-mini",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "api_id": "OPENAI_API_KEY",
        "is_active": 0,
        "model_type": "openai",
    },
    {
        "name": "DeepSeek Chat",
        "api_url": "https://api.deepseek.com/v1/chat/completions",
        "api_id": "DEEPSEEK_API_KEY",
        "is_active": 0,
        "model_type": "openai",
    },
]


@dataclass
class Prompt:
    id: int
    created_at: str
    prompt: str
    tags: str | None


@dataclass
class Model:
    id: int
    name: str
    api_url: str
    api_id: str
    is_active: bool
    model_type: str | None


@dataclass
class Result:
    id: int
    created_at: str
    prompt_id: int | None
    model_id: int
    prompt_text: str
    response: str


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _row_to_prompt(row: sqlite3.Row) -> Prompt:
    return Prompt(
        id=row["id"],
        created_at=row["created_at"],
        prompt=row["prompt"],
        tags=row["tags"],
    )


def _row_to_model(row: sqlite3.Row) -> Model:
    return Model(
        id=row["id"],
        name=row["name"],
        api_url=row["api_url"],
        api_id=row["api_id"],
        is_active=bool(row["is_active"]),
        model_type=row["model_type"],
    )


def _row_to_result(row: sqlite3.Row) -> Result:
    return Result(
        id=row["id"],
        created_at=row["created_at"],
        prompt_id=row["prompt_id"],
        model_id=row["model_id"],
        prompt_text=row["prompt_text"],
        response=row["response"],
    )


class Database:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, value),
                )
            for model in SEED_MODELS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO models (name, api_url, api_id, is_active, model_type)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        model["name"],
                        model["api_url"],
                        model["api_id"],
                        model["is_active"],
                        model["model_type"],
                    ),
                )
            conn.commit()

    # --- settings ---

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return default
        return row["value"]

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            conn.commit()

    # --- prompts ---

    def create_prompt(self, prompt: str, tags: str | None = None) -> int:
        created_at = _now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO prompts (created_at, prompt, tags) VALUES (?, ?, ?)",
                (created_at, prompt, tags),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_prompt(self, prompt_id: int) -> Prompt | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM prompts WHERE id = ?", (prompt_id,)
            ).fetchone()
        return _row_to_prompt(row) if row else None

    def list_prompts(self, search: str | None = None) -> list[Prompt]:
        query = "SELECT * FROM prompts"
        params: list[Any] = []
        if search:
            query += " WHERE prompt LIKE ? OR IFNULL(tags, '') LIKE ?"
            pattern = f"%{search}%"
            params.extend([pattern, pattern])
        query += " ORDER BY created_at DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_prompt(row) for row in rows]

    def delete_prompt(self, prompt_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
            conn.commit()

    # --- models ---

    def create_model(
        self,
        name: str,
        api_url: str,
        api_id: str,
        is_active: bool = True,
        model_type: str | None = "openai",
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO models (name, api_url, api_id, is_active, model_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, api_url, api_id, int(is_active), model_type),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_model(self, model_id: int) -> Model | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM models WHERE id = ?", (model_id,)
            ).fetchone()
        return _row_to_model(row) if row else None

    def list_models(self, active_only: bool = False) -> list[Model]:
        query = "SELECT * FROM models"
        params: list[Any] = []
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY name"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_model(row) for row in rows]

    def update_model(
        self,
        model_id: int,
        name: str,
        api_url: str,
        api_id: str,
        is_active: bool,
        model_type: str | None = "openai",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE models
                SET name = ?, api_url = ?, api_id = ?, is_active = ?, model_type = ?
                WHERE id = ?
                """,
                (name, api_url, api_id, int(is_active), model_type, model_id),
            )
            conn.commit()

    def set_model_active(self, model_id: int, is_active: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE models SET is_active = ? WHERE id = ?",
                (int(is_active), model_id),
            )
            conn.commit()

    def delete_model(self, model_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
            conn.commit()

    # --- results ---

    def create_result(
        self,
        model_id: int,
        prompt_text: str,
        response: str,
        prompt_id: int | None = None,
    ) -> int:
        created_at = _now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO results (created_at, prompt_id, model_id, prompt_text, response)
                VALUES (?, ?, ?, ?, ?)
                """,
                (created_at, prompt_id, model_id, prompt_text, response),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def list_results(
        self,
        search: str | None = None,
        prompt_id: int | None = None,
        model_id: int | None = None,
    ) -> list[Result]:
        query = "SELECT * FROM results WHERE 1 = 1"
        params: list[Any] = []
        if prompt_id is not None:
            query += " AND prompt_id = ?"
            params.append(prompt_id)
        if model_id is not None:
            query += " AND model_id = ?"
            params.append(model_id)
        if search:
            query += " AND (prompt_text LIKE ? OR response LIKE ?)"
            pattern = f"%{search}%"
            params.extend([pattern, pattern])
        query += " ORDER BY created_at DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_result(row) for row in rows]


def init_database(db_path: str | Path | None = None) -> Database:
    database = Database(db_path)
    database.init_db()
    return database
