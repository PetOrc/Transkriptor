# diarization.py
import re
import logging
from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QLabel, QColorDialog, QMessageBox
)
from PySide6.QtGui import QColor

try:
    from pyannote.audio import Pipeline  # noqa: F401
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False


class Diarizer:
    """Класс для автоматического определения говорящих и управления спикерами."""

    DEFAULT_COLORS = ["#1E88E5", "#43A047", "#E53935", "#FB8C00", "#8E24AA", "#00ACC1"]

    def __init__(self, pause_threshold: float = 2.0):
        self.pause_threshold = pause_threshold

    def diarize_segments(
        self,
        segments: List[Dict[str, Any]],
        max_speakers: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Размечает сегменты спикерами.
        Использует эвристику по паузам между сегментами (или pyannote при наличии токена).
        """
        if not segments:
            return []

        current_speaker_idx = 0
        prev_end = segments[0].get("start", 0.0)

        for seg in segments:
            start = float(seg.get("start", 0.0))
            pause = start - prev_end
            if pause >= self.pause_threshold:
                current_speaker_idx = (current_speaker_idx + 1) % max_speakers

            seg["speaker"] = f"Спикер {current_speaker_idx + 1}"
            prev_end = float(seg.get("end", start))

        logging.info("Диаризация сегментов успешно выполнена.")
        return segments

    def apply_diarization_to_text(self, text: str, speakers: List[Dict[str, str]]) -> str:
        """
        Добавляет разметку [Спикер X] к строкам в редакторе, если она ещё не проставлена.
        Формат строки: [000123] [Спикер 1] Текст
        """
        if not text.strip():
            return text

        speaker_names = [s["name"] for s in speakers] if speakers else ["Спикер 1", "Спикер 2"]
        lines = text.splitlines()
        new_lines = []
        speaker_idx = 0
        prev_seconds = 0

        pattern = re.compile(r"^(\[\d{6}\])\s*(?:\[([^\]]+)\]\s*)?(.*)$")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            match = pattern.match(stripped)
            if match:
                ts_code, existing_speaker, content = match.groups()
                cur_seconds = self.timestamp_to_seconds(ts_code)

                if existing_speaker:
                    speaker_label = existing_speaker
                else:
                    if cur_seconds - prev_seconds >= 6 and prev_seconds > 0:
                        speaker_idx = (speaker_idx + 1) % len(speaker_names)
                    speaker_label = speaker_names[speaker_idx]

                prev_seconds = cur_seconds
                new_lines.append(f"{ts_code} [{speaker_label}] {content}")
            else:
                speaker_label = speaker_names[speaker_idx % len(speaker_names)]
                new_lines.append(f"[{speaker_label}] {stripped}")
                speaker_idx += 1

        return "\n".join(new_lines)

    @staticmethod
    def seconds_to_timestamp(seconds: float) -> str:
        """Форматирует время в секундах в 6-значный тайм-код [000123] (ЧЧММСС)."""
        total_sec = max(0, int(round(seconds)))
        hrs = total_sec // 3600
        mins = (total_sec % 3600) // 60
        secs = total_sec % 60
        return f"[{hrs:02d}{mins:02d}{secs:02d}]"

    @staticmethod
    def timestamp_to_seconds(ts_str: str) -> int:
        """Переводит тайм-код формата [000123] (ЧЧММСС или секунды) в секунды."""
        digits = re.sub(r"\D", "", ts_str)
        if len(digits) != 6:
            return int(digits) if digits.isdigit() else 0

        hrs = int(digits[0:2])
        mins = int(digits[2:4])
        secs = int(digits[4:6])

        # Если последние две цифры и минуты укладываются в ЧЧММСС
        if mins < 60 and secs < 60:
            return hrs * 3600 + mins * 60 + secs
        return int(digits)


class DiarizationDialog(QDialog):
    """Диалоговое окно управления спикерами (переименование и назначение цвета)."""

    def __init__(self, speakers: List[Dict[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Диаризация — управление спикерами")
        self.resize(440, 320)

        # Копируем список спикеров и запоминаем старые имена для автозамены в тексте
        self.speakers: List[Dict[str, str]] = [
            {"old_name": s["name"], "name": s["name"], "color": s["color"]}
            for s in speakers
        ]

        self._init_ui()
        self._populate_list()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Список определенных спикеров:"))
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_row_selected)
        layout.addWidget(self.list_widget)

        edit_layout = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Имя спикера...")
        edit_layout.addWidget(self.name_edit)

        self.btn_rename = QPushButton("Переименовать")
        self.btn_rename.clicked.connect(self._rename_speaker)
        edit_layout.addWidget(self.btn_rename)

        self.btn_color = QPushButton("Выбрать цвет")
        self.btn_color.clicked.connect(self._choose_color)
        edit_layout.addWidget(self.btn_color)

        layout.addLayout(edit_layout)

        action_layout = QHBoxLayout()
        self.btn_add = QPushButton("Добавить спикера")
        self.btn_add.clicked.connect(self._add_speaker)
        action_layout.addWidget(self.btn_add)

        action_layout.addStretch()

        self.btn_ok = QPushButton("Применить")
        self.btn_ok.clicked.connect(self.accept)
        action_layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_cancel)

        layout.addLayout(action_layout)

    def _populate_list(self) -> None:
        self.list_widget.clear()
        for sp in self.speakers:
            item = QListWidgetItem(f"{sp['name']} ({sp['color']})")
            item.setForeground(QColor(sp["color"]))
            self.list_widget.addItem(item)

        if self.speakers:
            self.list_widget.setCurrentRow(0)

    def _on_row_selected(self, row: int) -> None:
        if 0 <= row < len(self.speakers):
            self.name_edit.setText(self.speakers[row]["name"])

    def _rename_speaker(self) -> None:
        row = self.list_widget.currentRow()
        new_name = self.name_edit.text().strip()
        if row < 0 or not new_name:
            QMessageBox.warning(self, "Внимание", "Выберите спикера и введите корректное имя.")
            return

        self.speakers[row]["name"] = new_name
        self._populate_list()
        self.list_widget.setCurrentRow(row)

    def _choose_color(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        current_color = QColor(self.speakers[row]["color"])
        color = QColorDialog.getColor(current_color, self, "Выберите цвет спикера")
        if color.isValid():
            self.speakers[row]["color"] = color.name()
            self._populate_list()
            self.list_widget.setCurrentRow(row)

    def _add_speaker(self) -> None:
        idx = len(self.speakers) + 1
        default_color = Diarizer.DEFAULT_COLORS[(idx - 1) % len(Diarizer.DEFAULT_COLORS)]
        new_name = f"Спикер {idx}"
        self.speakers.append({"old_name": new_name, "name": new_name, "color": default_color})
        self._populate_list()
        self.list_widget.setCurrentRow(len(self.speakers) - 1)

    def get_updated_speakers(self) -> List[Dict[str, str]]:
        """Возвращает обновлённый список спикеров."""
        return self.speakers