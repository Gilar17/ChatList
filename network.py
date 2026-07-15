"""HTTP-запросы к API нейросетей."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_TIMEOUT = 60


@dataclass
class ApiResponse:
    success: bool
    text: str


def get_api_key(api_id: str) -> str | None:
    value = os.getenv(api_id)
    if value is None or not value.strip():
        return None
    return value.strip()


def _build_openai_payload(prompt: str, model_name: str) -> dict:
    return {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
    }


def _parse_openai_response(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError) as exc:
        raise ValueError("Неожиданный формат ответа API") from exc


def send_chat_request(
    api_url: str,
    api_id: str,
    prompt: str,
    model_name: str,
    model_type: str | None = "openai",
    timeout: int = 60,
) -> ApiResponse:
    api_key = get_api_key(api_id)
    if api_key is None:
        return ApiResponse(
            success=False,
            text=f"API-ключ не найден: переменная окружения {api_id}",
        )

    adapter = (model_type or "openai").lower()
    if adapter not in {"openai", "deepseek", "groq"}:
        return ApiResponse(
            success=False,
            text=f"Неподдерживаемый тип модели: {model_type}",
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = _build_openai_payload(prompt, model_name)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        text = _parse_openai_response(data)
        return ApiResponse(success=True, text=text)
    except httpx.TimeoutException:
        return ApiResponse(success=False, text="Превышено время ожидания ответа API")
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip() or str(exc)
        return ApiResponse(
            success=False,
            text=f"Ошибка HTTP {exc.response.status_code}: {detail}",
        )
    except httpx.RequestError as exc:
        return ApiResponse(success=False, text=f"Ошибка сети: {exc}")
    except ValueError as exc:
        return ApiResponse(success=False, text=str(exc))
    except Exception as exc:  # noqa: BLE001
        return ApiResponse(success=False, text=f"Неожиданная ошибка: {exc}")
