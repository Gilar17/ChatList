"""Логика отправки промтов в нейросети и работы с временными результатами."""

from __future__ import annotations

from dataclasses import dataclass, field

import db
import network


@dataclass
class TempResult:
    model_id: int
    model_name: str
    response: str
    selected: bool = False


@dataclass
class PromptSession:
    prompt_text: str
    prompt_id: int | None = None
    results: list[TempResult] = field(default_factory=list)


class ModelService:
    def __init__(self, database: db.Database) -> None:
        self.database = database
        self.session = PromptSession(prompt_text="")

    def clear_temp_results(self) -> None:
        self.session = PromptSession(prompt_text=self.session.prompt_text)

    def get_active_models(self) -> list[db.Model]:
        return self.database.list_models(active_only=True)

    def send_prompt(self, prompt_text: str, prompt_id: int | None = None) -> list[TempResult]:
        prompt_text = prompt_text.strip()
        if not prompt_text:
            raise ValueError("Промт не может быть пустым")

        active_models = self.get_active_models()
        if not active_models:
            raise ValueError("Нет активных моделей. Активируйте модель в настройках.")

        timeout = int(self.database.get_setting("request_timeout", "60") or "60")
        results: list[TempResult] = []

        for model in active_models:
            api_result = network.send_chat_request(
                api_url=model.api_url,
                api_id=model.api_id,
                prompt=prompt_text,
                model_name=model.name,
                model_type=model.model_type,
                timeout=timeout,
            )
            results.append(
                TempResult(
                    model_id=model.id,
                    model_name=model.name,
                    response=api_result.text,
                    selected=False,
                )
            )

        self.session = PromptSession(
            prompt_text=prompt_text,
            prompt_id=prompt_id,
            results=results,
        )
        return results

    def save_selected_results(self) -> int:
        selected = [item for item in self.session.results if item.selected]
        if not selected:
            raise ValueError("Не выбрано ни одного результата для сохранения")

        saved_count = 0
        for item in selected:
            self.database.create_result(
                model_id=item.model_id,
                prompt_text=self.session.prompt_text,
                response=item.response,
                prompt_id=self.session.prompt_id,
            )
            saved_count += 1

        self.clear_temp_results()
        return saved_count

    def set_result_selected(self, index: int, selected: bool) -> None:
        if 0 <= index < len(self.session.results):
            self.session.results[index].selected = selected
