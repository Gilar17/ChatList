import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import db
from models import ModelService, TempResult


class SendPromptWorker(QThread):
    finished = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, service: ModelService, prompt_text: str, prompt_id: int | None) -> None:
        super().__init__()
        self.service = service
        self.prompt_text = prompt_text
        self.prompt_id = prompt_id

    def run(self) -> None:
        try:
            results = self.service.send_prompt(self.prompt_text, self.prompt_id)
            self.finished.emit(results)
        except ValueError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Неожиданная ошибка: {exc}")


class MainWindow(QMainWindow):
    def __init__(self, database: db.Database) -> None:
        super().__init__()
        self.database = database
        self.service = ModelService(database)
        self.worker: SendPromptWorker | None = None
        self.selected_prompt_id: int | None = None

        self.setWindowTitle("ChatList")
        self.resize(900, 600)

        self.prompt_combo = QComboBox()
        self.prompt_combo.setPlaceholderText("Выберите сохранённый промт")
        self.prompt_combo.currentIndexChanged.connect(self.on_prompt_selected)

        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Введите промт...")
        self.prompt_input.setMaximumHeight(120)

        self.send_button = QPushButton("Отправить")
        self.save_prompt_button = QPushButton("Сохранить промт")
        self.clear_button = QPushButton("Очистить")
        self.save_results_button = QPushButton("Сохранить")
        self.save_results_button.setEnabled(False)

        self.send_button.clicked.connect(self.on_send_clicked)
        self.save_prompt_button.clicked.connect(self.on_save_prompt_clicked)
        self.clear_button.clicked.connect(self.on_clear_clicked)
        self.save_results_button.clicked.connect(self.on_save_results_clicked)

        prompt_buttons = QHBoxLayout()
        prompt_buttons.addWidget(self.send_button)
        prompt_buttons.addWidget(self.save_prompt_button)
        prompt_buttons.addWidget(self.clear_button)
        prompt_buttons.addStretch()
        prompt_buttons.addWidget(self.save_results_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)

        self.status_label = QLabel("")
        self.status_label.setVisible(False)

        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(["", "Модель", "Ответ"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.itemChanged.connect(self.on_result_checkbox_changed)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Сохранённые промты"))
        layout.addWidget(self.prompt_combo)
        layout.addWidget(QLabel("Промт"))
        layout.addWidget(self.prompt_input)
        layout.addLayout(prompt_buttons)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("Результаты"))
        layout.addWidget(self.results_table)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.reload_prompts()

    def reload_prompts(self) -> None:
        self.prompt_combo.blockSignals(True)
        self.prompt_combo.clear()
        self.prompt_combo.addItem("— Новый промт —", None)
        for prompt in self.database.list_prompts():
            label = prompt.prompt.replace("\n", " ")
            if len(label) > 80:
                label = label[:77] + "..."
            self.prompt_combo.addItem(label, prompt.id)
        self.prompt_combo.blockSignals(False)

    def on_prompt_selected(self, index: int) -> None:
        if index < 0:
            return
        prompt_id = self.prompt_combo.itemData(index)
        self.selected_prompt_id = prompt_id
        if prompt_id is None:
            return
        prompt = self.database.get_prompt(prompt_id)
        if prompt:
            self.prompt_input.setPlainText(prompt.prompt)

    def set_loading(self, loading: bool, message: str = "") -> None:
        self.progress_bar.setVisible(loading)
        self.status_label.setVisible(loading)
        self.status_label.setText(message)
        self.send_button.setEnabled(not loading)
        self.save_prompt_button.setEnabled(not loading)
        self.clear_button.setEnabled(not loading)
        self.save_results_button.setEnabled(not loading and bool(self.service.session.results))

    def on_send_clicked(self) -> None:
        prompt_text = self.prompt_input.toPlainText().strip()
        if not prompt_text:
            QMessageBox.warning(self, "ChatList", "Введите текст промта.")
            return

        self.service.clear_temp_results()
        self.populate_results_table([])

        prompt_id = self.selected_prompt_id
        if self.prompt_combo.currentData() is None:
            prompt_id = None

        self.set_loading(True, "Отправка запросов в нейросети...")
        self.worker = SendPromptWorker(self.service, prompt_text, prompt_id)
        self.worker.finished.connect(self.on_send_finished)
        self.worker.failed.connect(self.on_send_failed)
        self.worker.start()

    def on_send_finished(self, results: list[TempResult]) -> None:
        self.set_loading(False)
        self.populate_results_table(results)
        self.save_results_button.setEnabled(bool(results))

    def on_send_failed(self, message: str) -> None:
        self.set_loading(False)
        QMessageBox.warning(self, "ChatList", message)

    def populate_results_table(self, results: list[TempResult]) -> None:
        self.results_table.blockSignals(True)
        self.results_table.setRowCount(0)
        for index, result in enumerate(results):
            self.results_table.insertRow(index)

            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            checkbox_item.setCheckState(
                Qt.CheckState.Checked if result.selected else Qt.CheckState.Unchecked
            )
            self.results_table.setItem(index, 0, checkbox_item)

            model_item = QTableWidgetItem(result.model_name)
            self.results_table.setItem(index, 1, model_item)

            response_item = QTableWidgetItem(result.response)
            self.results_table.setItem(index, 2, response_item)
        self.results_table.blockSignals(False)

    def on_result_checkbox_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        row = item.row()
        selected = item.checkState() == Qt.CheckState.Checked
        self.service.set_result_selected(row, selected)

    def on_save_prompt_clicked(self) -> None:
        prompt_text = self.prompt_input.toPlainText().strip()
        if not prompt_text:
            QMessageBox.warning(self, "ChatList", "Нечего сохранять: промт пуст.")
            return
        self.database.create_prompt(prompt_text)
        self.reload_prompts()
        QMessageBox.information(self, "ChatList", "Промт сохранён.")

    def on_clear_clicked(self) -> None:
        self.prompt_input.clear()
        self.prompt_combo.setCurrentIndex(0)
        self.selected_prompt_id = None
        self.service.clear_temp_results()
        self.populate_results_table([])
        self.save_results_button.setEnabled(False)

    def on_save_results_clicked(self) -> None:
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item is None:
                continue
            selected = item.checkState() == Qt.CheckState.Checked
            self.service.set_result_selected(row, selected)

        try:
            saved_count = self.service.save_selected_results()
        except ValueError as exc:
            QMessageBox.warning(self, "ChatList", str(exc))
            return

        self.populate_results_table([])
        self.save_results_button.setEnabled(False)
        QMessageBox.information(
            self,
            "ChatList",
            f"Сохранено результатов: {saved_count}",
        )


if __name__ == "__main__":
    database = db.init_database()
    app = QApplication(sys.argv)
    window = MainWindow(database)
    window.show()
    sys.exit(app.exec())
