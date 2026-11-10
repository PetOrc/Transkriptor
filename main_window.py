# main_window.py
import os
import re
import logging
from typing import List, Dict, Any, Optional

from PySide6.QtCore import Qt, QUrl, QSettings
from PySide6.QtGui import (
    QAction, QKeySequence, QTextCursor, QTextDocument,
    QDesktopServices, QTextCharFormat, QColor, QShortcut
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QComboBox, QCheckBox, QProgressBar,
    QTextEdit, QFileDialog, QMessageBox, QGroupBox, QFormLayout,
    QDialog, QLineEdit, QListWidget, QListWidgetItem, QSlider,
    QStackedWidget
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from database import DatabaseManager
from transcriber import Transcriber, TranscriptionWorker
from postprocessing import PostProcessor
from exporter import Exporter
from settings_dialog import SettingsDialog
from export_dialog import ExportDialog


class SyncTextEdit(QTextEdit):
    """Текстовый редактор с отслеживанием клика по строке для синхронизации с тайм-кодом."""

    def __init__(self, on_line_clicked_callback, parent=None):
        super().__init__(parent)
        self.on_line_clicked_callback = on_line_clicked_callback

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self.on_line_clicked_callback:
            cursor = self.textCursor()
            line_text = cursor.block().text()
            self.on_line_clicked_callback(line_text)


class FindReplaceDialog(QDialog):
    """Дополнительное окно «Поиск и замена»."""

    def __init__(self, text_edit: QTextEdit, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Поиск и замена")
        self.resize(420, 190)
        self.text_edit = text_edit
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.edit_find = QLineEdit()
        self.edit_find.setPlaceholderText("Введите текст для поиска...")
        form.addRow("Найти:", self.edit_find)

        self.edit_replace = QLineEdit()
        self.edit_replace.setPlaceholderText("Введите текст для замены...")
        form.addRow("Заменить на:", self.edit_replace)

        self.chk_case = QCheckBox("Учитывать регистр")
        form.addRow("", self.chk_case)
        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        self.btn_find_next = QPushButton("Найти далее")
        self.btn_find_next.clicked.connect(self.find_next)
        btn_layout.addWidget(self.btn_find_next)

        self.btn_replace = QPushButton("Заменить")
        self.btn_replace.clicked.connect(self.replace_one)
        btn_layout.addWidget(self.btn_replace)

        self.btn_replace_all = QPushButton("Заменить все")
        self.btn_replace_all.clicked.connect(self.replace_all)
        btn_layout.addWidget(self.btn_replace_all)

        layout.addLayout(btn_layout)

    def _get_find_flags(self):
        flags = QTextDocument.FindFlags()
        if self.chk_case.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        return flags

    def find_next(self) -> bool:
        query = self.edit_find.text()
        if not query:
            return False

        found = self.text_edit.find(query, self._get_find_flags())
        if not found:
            # Переход в начало документа при достижении конца
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.text_edit.setTextCursor(cursor)
            found = self.text_edit.find(query, self._get_find_flags())
            if not found:
                QMessageBox.information(self, "Поиск", f"Совпадений для «{query}» не найдено.")
        return found

    def replace_one(self) -> None:
        query = self.edit_find.text()
        replacement = self.edit_replace.text()
        if not query:
            return

        cursor = self.text_edit.textCursor()
        if cursor.hasSelection() and (
            cursor.selectedText() == query
            or (not self.chk_case.isChecked() and cursor.selectedText().lower() == query.lower())
        ):
            cursor.insertText(replacement)

        self.find_next()

    def replace_all(self) -> None:
        query = self.edit_find.text()
        replacement = self.edit_replace.text()
        if not query:
            return

        content = self.text_edit.toPlainText()
        flags = 0 if self.chk_case.isChecked() else re.IGNORECASE
        new_content, count = re.subn(re.escape(query), replacement, content, flags=flags)

        if count > 0:
            self.text_edit.setPlainText(new_content)
            QMessageBox.information(self, "Замена завершена", f"Выполнено замен: {count}.")
        else:
            QMessageBox.information(self, "Замена", "Совпадений не найдено.")


class HelpDialog(QDialog):
    """Окно «Справка» с кратким руководством пользователя."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Справка — Руководство пользователя")
        self.resize(560, 420)
        layout = QVBoxLayout(self)

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setHtml("""
            <h2>Руководство пользователя «Транскриптор»</h2>
            <p><b>1. Загрузка медиафайлов:</b> Нажмите <i>Файл → Открыть медиафайл (Ctrl+O)</i>.
            Поддерживаются форматы MP3, WAV, MP4, AVI, MKV.</p>
            <p><b>2. Настройка и запуск транскрипции:</b> На правой панели выберите модель Whisper
            (tiny, base, small, medium, large), язык (ru, en, auto), устройство (CPU или CUDA) и
            дополнительные опции, после чего нажмите кнопку <b>«Расшифровать»</b>.</p>
            <p><b>3. Синхронизация с тайм-кодами:</b> Каждая реплика имеет формат <code>[000123] Текст</code>
            (где 000123 — время ЧЧММСС). Кликните левой кнопкой мыши на любую строку с тайм-кодом,
            чтобы перемотать встроенный плеер на этот момент.</p>
            <p><b>4. Постобработка:</b> Используйте инструменты для расстановки знаков препинания и удаления слов-паразитов.</p>
            <p><b>5. Горячие клавиши:</b></p>
            <ul>
                <li><b>Space</b> — Воспроизведение / Пауза плеера</li>
                <li><b>Ctrl+O</b> — Открыть медиафайл</li>
                <li><b>Ctrl+S</b> — Сохранить проект в базу SQLite</li>
                <li><b>Ctrl+E</b> — Экспорт в SRT, TXT или DOCX</li>
                <li><b>Ctrl+F</b> — Поиск и замена</li>
                <li><b>F1</b> — Справка</li>
            </ul>
        """)
        layout.addWidget(help_text)

        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


class OpenProjectDialog(QDialog):
    """Диалоговое окно выбора ранее сохранённого проекта из базы SQLite."""

    def __init__(self, projects: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Открыть проект из базы данных")
        self.resize(450, 300)
        self.projects = projects
        self.selected_project_id: Optional[int] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Выберите ранее сохранённый проект:"))

        self.list_widget = QListWidget()
        for p in projects:
            item = QListWidgetItem(f"#{p['id']} — {p['name']} (создан: {p['created_at']})")
            item.setData(Qt.UserRole, p["id"])
            self.list_widget.addItem(item)

        self.list_widget.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_open = QPushButton("Загрузить")
        btn_open.clicked.connect(self._accept_selection)
        btn_layout.addWidget(btn_open)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _accept_selection(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "Внимание", "Выберите проект из списка.")
            return
        self.selected_project_id = item.data(Qt.UserRole)
        self.accept()


class MainWindow(QMainWindow):
    """Главное окно десктопного приложения «Транскриптор»."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Транскриптор — Автоматическая расшифровка аудио и видео")
        self.resize(1240, 780)

        # Инициализация сервисных модулей
        self.db = DatabaseManager()
        self.transcriber = Transcriber()
        self.postprocessor = PostProcessor()
        self.exporter = Exporter()

        # Состояние текущего проекта
        self.current_project_id: Optional[int] = None
        self.current_media_path: str = ""
        self.current_media_type: str = "audio"
        self.current_media_duration: float = 0.0
        self.worker: Optional[TranscriptionWorker] = None

        self.speakers: List[Dict[str, str]] = []

        self.app_settings: Dict[str, Any] = {
            "theme": "Тёмная",
            "autosave": True,
            "stay_on_top": False,
            "model": "base",
            "language": "ru",
            "device": "CPU",
            "model_path": QSettings("PetOrc", "Transkriptor").value("model_path", "", type=str)
        }

        self._init_player()
        self._init_ui()
        self._init_menu()
        self._init_shortcuts()
        self.apply_theme(self.app_settings["theme"])

    def _init_player(self) -> None:
        """Настраивает мультимедийный плеер QMediaPlayer и аудиовыход."""
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)

        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.positionChanged.connect(self._on_position_changed)

    def _init_ui(self) -> None:
        """Создаёт компоновку главного окна: левая, центральная, правая и нижняя панели."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)

        splitter = QSplitter(Qt.Horizontal)

        # 1. ЛЕВАЯ ПАНЕЛЬ: видео/аудио плеер и метаданные файла
        left_panel = QGroupBox("Медиаплеер и информация о файле")
        left_layout = QVBoxLayout(left_panel)

        self.player_stack = QStackedWidget()
        self.video_widget = QVideoWidget()
        self.media_player.setVideoOutput(self.video_widget)

        self.audio_placeholder = QLabel("Аудиорежим\n(Загрузите медиафайл через Файл → Открыть)")
        self.audio_placeholder.setAlignment(Qt.AlignCenter)
        self.audio_placeholder.setStyleSheet("border: 1px dashed #666; padding: 20px; font-size: 14px;")

        self.player_stack.addWidget(self.audio_placeholder)
        self.player_stack.addWidget(self.video_widget)
        left_layout.addWidget(self.player_stack, stretch=1)

        self.slider_position = QSlider(Qt.Horizontal)
        self.slider_position.setRange(0, 0)
        self.slider_position.sliderMoved.connect(self.media_player.setPosition)
        left_layout.addWidget(self.slider_position)

        self.lbl_time_code = QLabel("00:00:00 / 00:00:00")
        self.lbl_time_code.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.lbl_time_code)

        info_form = QFormLayout()
        self.lbl_file_name = QLabel("Не выбран")
        self.lbl_file_duration = QLabel("0 сек")
        self.lbl_file_size = QLabel("0 МБ")
        info_form.addRow("Имя файла:", self.lbl_file_name)
        info_form.addRow("Длительность:", self.lbl_file_duration)
        info_form.addRow("Размер:", self.lbl_file_size)
        left_layout.addLayout(info_form)

        splitter.addWidget(left_panel)

        # 2. ЦЕНТРАЛЬНАЯ ОБЛАСТЬ: редактор текста и индикатор прогресса
        center_panel = QGroupBox("Редактор транскрипции (клик по строке [000123] перематывает плеер)")
        center_layout = QVBoxLayout(center_panel)

        self.text_editor = SyncTextEdit(self._on_transcript_line_clicked)
        self.text_editor.setPlaceholderText(
            "Здесь появится расшифрованный текст с тайм-кодами в формате:\n"
            "[000005] Привет всем, начинаем запись..."
        )
        center_layout.addWidget(self.text_editor, stretch=1)

        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar, stretch=1)

        self.btn_cancel_transcribe = QPushButton("Отменить")
        self.btn_cancel_transcribe.setEnabled(False)
        self.btn_cancel_transcribe.clicked.connect(self.cancel_transcription)
        progress_layout.addWidget(self.btn_cancel_transcribe)

        center_layout.addLayout(progress_layout)
        self.lbl_status = QLabel("Статус: Готов к работе")
        center_layout.addWidget(self.lbl_status)

        splitter.addWidget(center_panel)

        # 3. ПРАВАЯ ПАНЕЛЬ: настройки транскрипции
        right_panel = QGroupBox("Настройка транскрипции")
        right_layout = QVBoxLayout(right_panel)
        right_form = QFormLayout()

        self.combo_model = QComboBox()
        self.combo_model.addItems(["tiny", "base", "small", "medium", "large"])
        self.combo_model.setCurrentText("base")
        right_form.addRow("Модель Whisper:", self.combo_model)

        model_path_layout = QHBoxLayout()
        self.edit_model_path = QLineEdit(self.app_settings.get("model_path", ""))
        self.edit_model_path.setPlaceholderText("Папка или файл локальной модели .pt (необязательно)")
        model_path_layout.addWidget(self.edit_model_path)
        self.btn_model_path = QPushButton("Обзор...")
        self.btn_model_path.clicked.connect(self.select_model_path)
        model_path_layout.addWidget(self.btn_model_path)
        right_form.addRow("Локальная модель:", model_path_layout)

        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["ru", "en", "auto"])
        self.combo_lang.setCurrentText("ru")
        right_form.addRow("Язык:", self.combo_lang)

        self.combo_device = QComboBox()
        self.combo_device.addItems(["CPU", "CUDA (GPU)"])
        right_form.addRow("Устройство:", self.combo_device)

        right_layout.addLayout(right_form)

        self.chk_punctuation = QCheckBox("Умная пунктуация")
        self.chk_punctuation.setChecked(True)
        right_layout.addWidget(self.chk_punctuation)

        self.chk_filler_filter = QCheckBox("Фильтр слов-паразитов")
        self.chk_filler_filter.setChecked(True)
        right_layout.addWidget(self.chk_filler_filter)

        self.btn_start_transcribe = QPushButton("Расшифровать")
        self.btn_start_transcribe.setMinimumHeight(40)
        self.btn_start_transcribe.clicked.connect(self.start_transcription)
        right_layout.addWidget(self.btn_start_transcribe)

        self.btn_open_media = QPushButton("Загрузить медиафайл...")
        self.btn_open_media.clicked.connect(self.open_media_file)
        right_layout.addWidget(self.btn_open_media)

        right_layout.addStretch()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 2)
        root_layout.addWidget(splitter, stretch=1)

        # 4. НИЖНЯЯ ПАНЕЛЬ: кнопки управления текстом и плеером
        bottom_panel = QGroupBox("Панель управления и воспроизведения")
        bottom_layout = QHBoxLayout(bottom_panel)

        # Управление плеером
        self.btn_play_pause = QPushButton("▶ Play / Pause")
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)
        bottom_layout.addWidget(self.btn_play_pause)

        self.btn_seek_back = QPushButton("⏪ -5 сек")
        self.btn_seek_back.clicked.connect(lambda: self.seek_relative(-5000))
        bottom_layout.addWidget(self.btn_seek_back)

        self.btn_seek_forward = QPushButton("⏩ +5 сек")
        self.btn_seek_forward.clicked.connect(lambda: self.seek_relative(5000))
        bottom_layout.addWidget(self.btn_seek_forward)

        bottom_layout.addWidget(QLabel("Скорость:"))
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.5x", "1x", "1.5x", "2x"])
        self.combo_speed.setCurrentText("1x")
        self.combo_speed.currentTextChanged.connect(self.change_playback_speed)
        bottom_layout.addWidget(self.combo_speed)

        bottom_layout.addStretch()

        # Управление текстом и обработкой
        self.btn_find = QPushButton("Найти")
        self.btn_find.clicked.connect(self.open_find_replace_dialog)
        bottom_layout.addWidget(self.btn_find)

        self.btn_replace = QPushButton("Заменить")
        self.btn_replace.clicked.connect(self.open_find_replace_dialog)
        bottom_layout.addWidget(self.btn_replace)

        self.btn_clear = QPushButton("Очистить текст")
        self.btn_clear.clicked.connect(self.clear_transcript_text)
        bottom_layout.addWidget(self.btn_clear)

        self.btn_punctuate = QPushButton("Пунктуация")
        self.btn_punctuate.clicked.connect(self.run_manual_postprocessing)
        bottom_layout.addWidget(self.btn_punctuate)

        self.btn_export = QPushButton("Экспорт")
        self.btn_export.clicked.connect(self.open_export_dialog)
        bottom_layout.addWidget(self.btn_export)

        root_layout.addWidget(bottom_panel)

    def _init_menu(self) -> None:
        """Создаёт главное меню (Файл, Транскрипция, Редактор, Воспроизведение, Инструменты, Вид, Справка)."""
        menubar = self.menuBar()

        # 1. Меню «Файл»
        menu_file = menubar.addMenu("Файл")
        act_open_file = QAction("Открыть медиафайл...", self)
        act_open_file.setShortcut(QKeySequence("Ctrl+O"))
        act_open_file.triggered.connect(self.open_media_file)
        menu_file.addAction(act_open_file)

        act_open_proj = QAction("Открыть проект...", self)
        act_open_proj.triggered.connect(self.open_project_from_db)
        menu_file.addAction(act_open_proj)

        act_save_proj = QAction("Сохранить проект", self)
        act_save_proj.setShortcut(QKeySequence("Ctrl+S"))
        act_save_proj.triggered.connect(lambda: self.save_current_project(silent=False))
        menu_file.addAction(act_save_proj)

        act_export = QAction("Экспорт...", self)
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self.open_export_dialog)
        menu_file.addAction(act_export)

        menu_file.addSeparator()
        act_exit = QAction("Выход", self)
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # 2. Меню «Транскрипция»
        menu_transcribe = menubar.addMenu("Транскрипция")
        act_start = QAction("Расшифровать", self)
        act_start.triggered.connect(self.start_transcription)
        menu_transcribe.addAction(act_start)

        act_cancel = QAction("Отменить процесс", self)
        act_cancel.triggered.connect(self.cancel_transcription)
        menu_transcribe.addAction(act_cancel)

        # 3. Меню «Редактор»
        menu_editor = menubar.addMenu("Редактор")
        act_find = QAction("Поиск и замена...", self)
        act_find.setShortcut(QKeySequence("Ctrl+F"))
        act_find.triggered.connect(self.open_find_replace_dialog)
        menu_editor.addAction(act_find)

        act_clear = QAction("Очистить текст", self)
        act_clear.triggered.connect(self.clear_transcript_text)
        menu_editor.addAction(act_clear)

        # 4. Меню «Воспроизведение»
        menu_play = menubar.addMenu("Воспроизведение")
        act_play = QAction("Play / Pause", self)
        act_play.triggered.connect(self.toggle_play_pause)
        menu_play.addAction(act_play)

        act_back = QAction("Перемотка -5 сек", self)
        act_back.triggered.connect(lambda: self.seek_relative(-5000))
        menu_play.addAction(act_back)

        act_fwd = QAction("Перемотка +5 сек", self)
        act_fwd.triggered.connect(lambda: self.seek_relative(5000))
        menu_play.addAction(act_fwd)

        # 5. Меню «Инструменты»
        menu_tools = menubar.addMenu("Инструменты")
        act_punct = QAction("Расставить пунктуацию и очистить паразиты", self)
        act_punct.triggered.connect(self.run_manual_postprocessing)
        menu_tools.addAction(act_punct)

        menu_tools.addSeparator()
        act_settings = QAction("Настройки...", self)
        act_settings.triggered.connect(self.open_settings_dialog)
        menu_tools.addAction(act_settings)

        # 6. Меню «Вид»
        menu_view = menubar.addMenu("Вид")
        act_dark = QAction("Тёмная тема", self)
        act_dark.triggered.connect(lambda: self.apply_theme("Тёмная"))
        menu_view.addAction(act_dark)

        act_light = QAction("Светлая тема", self)
        act_light.triggered.connect(lambda: self.apply_theme("Светлая"))
        menu_view.addAction(act_light)

        menu_view.addSeparator()
        self.act_on_top = QAction("Поверх окон", self, checkable=True)
        self.act_on_top.triggered.connect(self.toggle_stay_on_top)
        menu_view.addAction(self.act_on_top)

        # 7. Меню «Справка»
        menu_help = menubar.addMenu("Справка")
        act_help = QAction("Руководство пользователя", self)
        act_help.setShortcut(QKeySequence("F1"))
        act_help.triggered.connect(self.open_help_dialog)
        menu_help.addAction(act_help)

    def _init_shortcuts(self) -> None:
        """Настраивает горячую клавишу Space для Play/Pause, когда фокус вне текстового редактора."""
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.shortcut_space.setContext(Qt.WindowShortcut)
        self.shortcut_space.activated.connect(self._handle_space_shortcut)

    def _handle_space_shortcut(self) -> None:
        if self.focusWidget() is not self.text_editor:
            self.toggle_play_pause()

    # -------------------- РАБОТА С МЕДИАФАЙЛАМИ И ПЛЕЕРОМ --------------------

    def select_model_path(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Выберите папку с моделью Whisper")
        if path:
            self.edit_model_path.setText(path)
            self.app_settings["model_path"] = path
            QSettings("PetOrc", "Transkriptor").setValue("model_path", path)

    def open_media_file(self) -> None:
        """Открывает аудио или видео файл и загружает его в QMediaPlayer."""
        try:
            file_filter = "Медиафайлы (*.mp3 *.wav *.m4a *.flac *.ogg *.aac *.mp4 *.avi *.mkv *.mov *.webm);;Все файлы (*.*)"
            path, _ = QFileDialog.getOpenFileName(self, "Выберите аудио или видео файл", "", file_filter)
            if not path:
                return

            self._load_media_from_path(path)
        except Exception as e:
            logging.error(f"Ошибка при открытии медиафайла: {e}", exc_info=True)
            QMessageBox.critical(self, "Ошибка загрузки файла", f"Не удалось загрузить файл:\n{e}")

    def _load_media_from_path(self, path: str) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Файл не найден: {path}")

        self.current_media_path = path
        ext = os.path.splitext(path)[1].lower()
        self.current_media_type = "video" if ext in Transcriber.VIDEO_EXTENSIONS else "audio"

        size_mb = os.path.getsize(path) / (1024 * 1024)
        self.lbl_file_name.setText(os.path.basename(path))
        self.lbl_file_size.setText(f"{size_mb:.2f} МБ")

        if self.current_media_type == "video":
            self.player_stack.setCurrentWidget(self.video_widget)
        else:
            self.audio_placeholder.setText(f"Аудиофайл:\n{os.path.basename(path)}")
            self.player_stack.setCurrentWidget(self.audio_placeholder)

        self.media_player.setSource(QUrl.fromLocalFile(path))
        self.lbl_status.setText(f"Статус: Загружен файл {os.path.basename(path)}")
        logging.info(f"Загружен медиафайл: {path}")

    def _on_duration_changed(self, duration_ms: int) -> None:
        self.slider_position.setRange(0, duration_ms)
        self.current_media_duration = duration_ms / 1000.0
        self.lbl_file_duration.setText(f"{int(self.current_media_duration)} сек")
        self._update_time_label(self.media_player.position(), duration_ms)

    def _on_position_changed(self, position_ms: int) -> None:
        if not self.slider_position.isSliderDown():
            self.slider_position.setValue(position_ms)
        self._update_time_label(position_ms, self.media_player.duration())

    def _update_time_label(self, pos_ms: int, dur_ms: int) -> None:
        def fmt(ms: int) -> str:
            s = max(0, ms // 1000)
            return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

        self.lbl_time_code.setText(f"{fmt(pos_ms)} / {fmt(dur_ms)}")

    def toggle_play_pause(self) -> None:
        if self.media_player.playbackState() == QMediaPlayer.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def seek_relative(self, delta_ms: int) -> None:
        new_pos = max(0, min(self.media_player.duration(), self.media_player.position() + delta_ms))
        self.media_player.setPosition(new_pos)

    def change_playback_speed(self, speed_text: str) -> None:
        try:
            rate = float(speed_text.replace("x", "").strip())
            self.media_player.setPlaybackRate(rate)
        except ValueError:
            pass

    def _on_transcript_line_clicked(self, line_text: str) -> None:
        """Перематывает плеер при клике на строку с тайм-кодом [000123]."""
        match = re.search(r"\[(\d{6})\]", line_text)
        if match:
            h, m, sec = int(match.group(1)[:2]), int(match.group(1)[2:4]), int(match.group(1)[4:6])
            seconds = h * 3600 + m * 60 + sec
            self.media_player.setPosition(seconds * 1000)
            self.lbl_status.setText(f"Статус: Перемотка плеера на {seconds} сек ({match.group(0)})")

    # -------------------- ТРАНСКРИПЦИЯ И ПОСТОБРАБОТКА --------------------

    def start_transcription(self) -> None:
        """Запускает процесс распознавания речи в отдельном потоке."""
        try:
            if self.worker and self.worker.isRunning():
                QMessageBox.information(self, "Внимание", "Транскрипция уже выполняется.")
                return

            if not self.current_media_path:
                reply = QMessageBox.question(
                    self,
                    "Медиафайл не выбран",
                    "Медиафайл не загружен. Запустить демонстрационную транскрипцию (mock-режим)?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return

            model_name = self.combo_model.currentText()
            language = self.combo_lang.currentText()
            device = self.combo_device.currentText()

            self.progress_bar.setValue(0)
            self.btn_start_transcribe.setEnabled(False)
            self.btn_cancel_transcribe.setEnabled(True)
            self.lbl_status.setText("Статус: Запуск транскрипции...")

            self.worker = TranscriptionWorker(
                transcriber=self.transcriber,
                media_path=self.current_media_path,
                language=language,
                model_name=model_name,
                device=device,
                model_path=self.edit_model_path.text().strip()
            )
            self.worker.progress_changed.connect(self._on_transcription_progress)
            self.worker.transcription_finished.connect(self._on_transcription_finished)
            self.worker.transcription_cancelled.connect(self._on_transcription_cancelled)
            self.worker.transcription_error.connect(self._on_transcription_error)
            self.worker.start()
        except Exception as e:
            logging.error(f"Ошибка запуска транскрипции: {e}", exc_info=True)
            QMessageBox.critical(self, "Ошибка", f"Не удалось запустить транскрипцию:\n{e}")

    def cancel_transcription(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.lbl_status.setText("Статус: Отмена транскрипции...")

    def _on_transcription_progress(self, percent: int, message: str) -> None:
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(f"Статус: {message}")

    def _on_transcription_cancelled(self) -> None:
        self.btn_start_transcribe.setEnabled(True)
        self.btn_cancel_transcribe.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Статус: Транскрипция отменена пользователем.")

    def _on_transcription_error(self, error_msg: str) -> None:
        self.btn_start_transcribe.setEnabled(True)
        self.btn_cancel_transcribe.setEnabled(False)
        self.lbl_status.setText("Статус: Ошибка транскрипции.")
        QMessageBox.critical(self, "Ошибка транскрипции", f"Произошла ошибка:\n{error_msg}")

    def _on_transcription_finished(self, segments: List[Dict[str, Any]]) -> None:
        """Формирует итоговый текст из сегментов, применяет диаризацию и постобработку."""
        try:
            self.btn_start_transcribe.setEnabled(True)
            self.btn_cancel_transcribe.setEnabled(False)

            lines: List[str] = []
            for seg in segments:
                seconds = max(0, int(float(seg.get("start", 0.0))))
                ts_code = f"[{seconds // 3600:02d}{(seconds % 3600) // 60:02d}{seconds % 60:02d}]"
                lines.append(f"{ts_code} {seg.get('text', '').strip()}")

            full_text = "\n".join(lines)

            if self.chk_filler_filter.isChecked():
                full_text = self.postprocessor.remove_filler_words(full_text)

            if self.chk_punctuation.isChecked():
                full_text = self.postprocessor.apply_smart_punctuation(full_text, self.combo_lang.currentText())

            self.text_editor.setPlainText(full_text)
            self.lbl_status.setText("Статус: Транскрипция и обработка успешно завершены.")
        except Exception as e:
            logging.error(f"Ошибка обработки результатов транскрипции: {e}", exc_info=True)
            QMessageBox.critical(self, "Ошибка", f"Не удалось обработать текст:\n{e}")

    def run_manual_postprocessing(self) -> None:
        """Запускает умную пунктуацию, фильтр слов-паразитов и разбивку на абзацы по кнопке."""
        try:
            text = self.text_editor.toPlainText()
            if not text.strip():
                QMessageBox.information(self, "Информация", "Поле текста пусто.")
                return

            if self.chk_filler_filter.isChecked():
                text = self.postprocessor.remove_filler_words(text)
            text = self.postprocessor.apply_smart_punctuation(text, self.combo_lang.currentText())

            self.text_editor.setPlainText(text)
            self._highlight_speakers_in_editor()
            self.lbl_status.setText("Статус: Постобработка текста выполнена.")
        except Exception as e:
            logging.error(f"Ошибка постобработки: {e}", exc_info=True)
            QMessageBox.critical(self, "Ошибка", f"Сбой постобработки:\n{e}")

    def clear_transcript_text(self) -> None:
        self.text_editor.clear()
        self.lbl_status.setText("Статус: Текст очищен.")

    # -------------------- ДОПОЛНИТЕЛЬНЫЕ ОКНА И ПРОЕКТЫ БД --------------------

    def open_find_replace_dialog(self) -> None:
        dlg = FindReplaceDialog(self.text_editor, self)
        dlg.exec()

    def open_settings_dialog(self) -> None:
        dlg = SettingsDialog(self.app_settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.app_settings.update(dlg.get_settings())
            self.combo_model.setCurrentText(self.app_settings["model"])
            self.combo_lang.setCurrentText(self.app_settings["language"])
            self.combo_device.setCurrentText(self.app_settings["device"])
            self.apply_theme(self.app_settings["theme"])
            self.act_on_top.setChecked(self.app_settings["stay_on_top"])
            self.toggle_stay_on_top(self.app_settings["stay_on_top"])
            self.lbl_status.setText("Статус: Настройки сохранены.")

    def open_export_dialog(self) -> None:
        """Открывает диалог экспорта и сохраняет результат в SRT, TXT или DOCX."""
        try:
            text = self.text_editor.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, "Экспорт невозможен", "Нет текста для экспорта.")
                return

            base_name = os.path.splitext(os.path.basename(self.current_media_path))[0] if self.current_media_path else "transcript"
            dlg = ExportDialog(default_name=base_name, parent=self)

            if dlg.exec() == QDialog.Accepted:
                opts = dlg.get_export_options()
                self.exporter.export(text, opts["path"], opts["format"])

                if self.current_project_id is not None:
                    self.db.log_export(self.current_project_id, opts["path"], opts["format"])

                QMessageBox.information(
                    self,
                    "Экспорт завершён",
                    f"Файл успешно сохранён в формате {opts['format']}:\n{opts['path']}"
                )

                if opts["open_folder"]:
                    folder = os.path.dirname(os.path.abspath(opts["path"]))
                    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        except Exception as e:
            logging.error(f"Ошибка экспорта: {e}", exc_info=True)
            QMessageBox.critical(self, "Ошибка экспорта", f"Не удалось выполнить экспорт:\n{e}")

    def open_help_dialog(self) -> None:
        dlg = HelpDialog(self)
        dlg.exec()

    def save_current_project(self, silent: bool = False) -> None:
        """Сохраняет проект и все связанные таблицы в SQLite."""
        try:
            proj_name = os.path.basename(self.current_media_path) if self.current_media_path else "Проект без медиафайла"
            media_info = {
                "path": self.current_media_path,
                "type": self.current_media_type,
                "duration": self.current_media_duration
            }
            settings_info = {
                "language": self.combo_lang.currentText(),
                "model": self.combo_model.currentText(),
                "punctuation": self.chk_punctuation.isChecked()
            }

            self.current_project_id = self.db.save_full_project(
                project_id=self.current_project_id,
                name=proj_name,
                media_info=media_info,
                settings_info=settings_info,
                transcription_text=self.text_editor.toPlainText(),
                status="saved",
                speakers_list=self.speakers
            )
            self.lbl_status.setText(f"Статус: Проект #{self.current_project_id} сохранён в БД.")
            if not silent:
                QMessageBox.information(self, "Сохранение проекта", f"Проект «{proj_name}» успешно сохранён.")
        except Exception as e:
            logging.error(f"Ошибка сохранения проекта: {e}", exc_info=True)
            if not silent:
                QMessageBox.critical(self, "Ошибка БД", f"Не удалось сохранить проект:\n{e}")

    def open_project_from_db(self) -> None:
        """Загружает ранее сохранённый проект через меню «Файл → Открыть проект»."""
        try:
            projects = self.db.get_all_projects()
            if not projects:
                QMessageBox.information(self, "Проекты", "В базе данных пока нет сохранённых проектов.")
                return

            dlg = OpenProjectDialog(projects, self)
            if dlg.exec() == QDialog.Accepted and dlg.selected_project_id is not None:
                data = self.db.load_project(dlg.selected_project_id)
                if not data:
                    return

                self.current_project_id = data["project"]["id"]
                if data["media"] and data["media"].get("path"):
                    media_path = data["media"]["path"]
                    if os.path.exists(media_path):
                        self._load_media_from_path(media_path)
                    else:
                        self.current_media_path = media_path
                        self.lbl_file_name.setText(f"{os.path.basename(media_path)} (не найден)")

                if data["settings"]:
                    st = data["settings"]
                    self.combo_lang.setCurrentText(st.get("language", "ru"))
                    self.combo_model.setCurrentText(st.get("model", "base"))
                    self.chk_punctuation.setChecked(bool(st.get("punctuation", 1)))

                if data["speakers"]:
                    self.speakers = data["speakers"]

                if data["transcription"]:
                    self.text_editor.setPlainText(data["transcription"].get("full_text", ""))
                    self._highlight_speakers_in_editor()

                self.lbl_status.setText(f"Статус: Загружен проект «{data['project']['name']}»")
        except Exception as e:
            logging.error(f"Ошибка открытия проекта из БД: {e}", exc_info=True)
            QMessageBox.critical(self, "Ошибка загрузки проекта", f"Не удалось открыть проект:\n{e}")

    # -------------------- ВИД, ТЕМЫ И ЗАКРЫТИЕ ОКНА --------------------

    def toggle_stay_on_top(self, checked: bool) -> None:
        """Переключает режим окна «Поверх окон» (WindowStaysOnTopHint)."""
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show()

    def apply_theme(self, theme_name: str) -> None:
        """Переключает тёмную и светлую темы оформления."""
        self.app_settings["theme"] = theme_name
        if theme_name == "Тёмная":
            self.setStyleSheet("""
                QMainWindow, QDialog, QWidget {
                    background-color: #1E1E2E;
                    color: #CDD6F4;
                    font-family: Segoe UI, sans-serif;
                    font-size: 13px;
                }
                QGroupBox {
                    border: 1px solid #45475A;
                    border-radius: 6px;
                    margin-top: 10px;
                    padding-top: 8px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 4px;
                }
                QTextEdit, QLineEdit, QListWidget, QComboBox, QSpinBox, QTableWidget {
                    background-color: #181825;
                    color: #CDD6F4;
                    border: 1px solid #45475A;
                    border-radius: 4px;
                    padding: 4px;
                }
                QPushButton {
                    background-color: #313244;
                    color: #CDD6F4;
                    border: 1px solid #585B70;
                    border-radius: 5px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #45475A;
                }
                QPushButton:disabled {
                    background-color: #181825;
                    color: #6C7086;
                }
                QProgressBar {
                    border: 1px solid #45475A;
                    border-radius: 4px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #89B4FA;
                }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow, QDialog, QWidget {
                    background-color: #F5F7FA;
                    color: #1F2937;
                    font-family: Segoe UI, sans-serif;
                    font-size: 13px;
                }
                QGroupBox {
                    border: 1px solid #D1D5DB;
                    border-radius: 6px;
                    margin-top: 10px;
                    padding-top: 8px;
                    font-weight: bold;
                }
                QTextEdit, QLineEdit, QListWidget, QComboBox, QSpinBox, QTableWidget {
                    background-color: #FFFFFF;
                    color: #1F2937;
                    border: 1px solid #CBD5E1;
                    border-radius: 4px;
                    padding: 4px;
                }
                QPushButton {
                    background-color: #E2E8F0;
                    color: #1E293B;
                    border: 1px solid #94A3B8;
                    border-radius: 5px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #CBD5E1;
                }
                QProgressBar {
                    border: 1px solid #CBD5E1;
                    border-radius: 4px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #2563EB;
                }
            """)

    def closeEvent(self, event) -> None:
        """Автоматически сохраняет проект в SQLite при закрытии окна."""
        try:
            if self.worker and self.worker.isRunning():
                self.worker.cancel()
                self.worker.wait(1000)

            if self.app_settings.get("autosave", True):
                has_content = bool(self.text_editor.toPlainText().strip() or self.current_media_path)
                if has_content:
                    self.save_current_project(silent=True)
        except Exception as e:
            logging.error(f"Ошибка при автосохранении во время закрытия: {e}", exc_info=True)
        super().closeEvent(event)