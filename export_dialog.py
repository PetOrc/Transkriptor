# export_dialog.py
import os
from typing import Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QPushButton, QCheckBox, QFileDialog, QMessageBox
)


class ExportDialog(QDialog):
    """Диалоговое окно выбора формата и пути сохранения для экспорта."""

    FORMAT_FILTERS = {
        "SRT": "Субтитры SubRip (*.srt)",
        "TXT": "Текстовый файл (*.txt)",
        "DOCX": "Документ Microsoft Word (*.docx)"
    }

    def __init__(self, default_name: str = "transcription", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Экспорт транскрипции")
        self.resize(480, 200)
        self.default_name = default_name
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.combo_format = QComboBox()
        self.combo_format.addItems(["SRT", "TXT", "DOCX"])
        self.combo_format.currentTextChanged.connect(self._update_extension)
        form_layout.addRow("Формат файла:", self.combo_format)

        path_layout = QHBoxLayout()
        default_path = os.path.abspath(f"{self.default_name}.srt")
        self.edit_path = QLineEdit(default_path)
        path_layout.addWidget(self.edit_path)

        self.btn_browse = QPushButton("Обзор...")
        self.btn_browse.clicked.connect(self._browse_path)
        path_layout.addWidget(self.btn_browse)

        form_layout.addRow("Путь сохранения:", path_layout)

        self.chk_open_folder = QCheckBox("Открыть папку после экспорта")
        self.chk_open_folder.setChecked(True)
        form_layout.addRow("", self.chk_open_folder)

        main_layout.addLayout(form_layout)
        main_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_export = QPushButton("Экспортировать")
        self.btn_export.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(self.btn_export)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        main_layout.addLayout(btn_layout)

    def _update_extension(self, fmt: str) -> None:
        current_path = self.edit_path.text().strip()
        if current_path:
            base, _ = os.path.splitext(current_path)
            self.edit_path.setText(f"{base}.{fmt.lower()}")

    def _browse_path(self) -> None:
        fmt = self.combo_format.currentText()
        file_filter = self.FORMAT_FILTERS.get(fmt, "Все файлы (*.*)")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Выберите путь для сохранения",
            self.edit_path.text(),
            file_filter
        )
        if path:
            self.edit_path.setText(path)

    def _validate_and_accept(self) -> None:
        if not self.edit_path.text().strip():
            QMessageBox.warning(self, "Ошибка", "Укажите путь сохранения файла.")
            return
        self.accept()

    def get_export_options(self) -> Dict[str, Any]:
        """Возвращает выбранные параметры экспорта."""
        return {
            "format": self.combo_format.currentText(),
            "path": self.edit_path.text().strip(),
            "open_folder": self.chk_open_folder.isChecked()
        }