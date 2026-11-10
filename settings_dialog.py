# settings_dialog.py
from typing import Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QComboBox, QCheckBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView
)


class SettingsDialog(QDialog):
    """Окно «Настройки» с вкладками: Общие, Транскрипция, Горячие клавиши."""

    def __init__(self, current_settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки приложения")
        self.resize(500, 380)
        self.settings = current_settings.copy()
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_general_tab(), "Общие")
        self.tabs.addTab(self._create_transcription_tab(), "Транскрипция")
        self.tabs.addTab(self._create_hotkeys_tab(), "Горячие клавиши")
        main_layout.addWidget(self.tabs)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QPushButton("Сохранить")
        self.btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        main_layout.addLayout(btn_layout)

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["Светлая", "Тёмная"])
        self.combo_theme.setCurrentText(self.settings.get("theme", "Тёмная"))
        layout.addRow("Тема оформления:", self.combo_theme)

        self.chk_autosave = QCheckBox("Автоматически сохранять проект при выходе")
        self.chk_autosave.setChecked(bool(self.settings.get("autosave", True)))
        layout.addRow("Автосохранение:", self.chk_autosave)

        self.chk_stay_on_top = QCheckBox("Закрепить окно поверх всех окон")
        self.chk_stay_on_top.setChecked(bool(self.settings.get("stay_on_top", False)))
        layout.addRow("Режим окна:", self.chk_stay_on_top)

        return widget

    def _create_transcription_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)

        self.combo_model = QComboBox()
        self.combo_model.addItems(["tiny", "base", "small", "medium", "large"])
        self.combo_model.setCurrentText(self.settings.get("model", "base"))
        layout.addRow("Модель Whisper по умолчанию:", self.combo_model)

        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["ru", "en", "auto"])
        self.combo_lang.setCurrentText(self.settings.get("language", "ru"))
        layout.addRow("Язык распознавания:", self.combo_lang)

        self.combo_device = QComboBox()
        self.combo_device.addItems(["CPU", "CUDA (GPU)"])
        self.combo_device.setCurrentText(self.settings.get("device", "CPU"))
        layout.addRow("Устройство вычислений:", self.combo_device)

        return widget

    def _create_hotkeys_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        table = QTableWidget(6, 2)
        table.setHorizontalHeaderLabels(["Действие", "Комбинация клавиш"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)

        hotkeys = [
            ("Воспроизведение / Пауза", "Space"),
            ("Открыть медиафайл", "Ctrl+O"),
            ("Сохранить проект", "Ctrl+S"),
            ("Экспорт транскрипции", "Ctrl+E"),
            ("Поиск и замена текста", "Ctrl+F"),
            ("Справка (руководство)", "F1"),
        ]

        for row, (action, key) in enumerate(hotkeys):
            table.setItem(row, 0, QTableWidgetItem(action))
            table.setItem(row, 1, QTableWidgetItem(key))

        layout.addWidget(table)
        return widget

    def get_settings(self) -> Dict[str, Any]:
        """Возвращает выбранные пользователем настройки."""
        return {
            "theme": self.combo_theme.currentText(),
            "autosave": self.chk_autosave.isChecked(),
            "stay_on_top": self.chk_stay_on_top.isChecked(),
            "model": self.combo_model.currentText(),
            "language": self.combo_lang.currentText(),
            "device": self.combo_device.currentText(),
        }