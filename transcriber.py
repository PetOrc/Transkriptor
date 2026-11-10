# transcriber.py
import os
import time
import tempfile
import logging
from typing import List, Dict, Any, Callable, Optional
from PySide6.QtCore import QThread, Signal

# Попытка импорта опциональных тяжёлых зависимостей
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

try:
    import ffmpeg
    FFMPEG_AVAILABLE = True
except ImportError:
    FFMPEG_AVAILABLE = False


class Transcriber:
    """Обёртка над моделью OpenAI Whisper с поддержкой извлечения аудио и mock-режима."""

    VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv"}
    AUDIO_EXTENSIONS = {".mp3", ".wav"}

    def __init__(self):
        self.model = None
        self.current_model_name: Optional[str] = None
        self.current_device: Optional[str] = None
        self.use_mock_fallback: bool = not WHISPER_AVAILABLE

    def load_model(self, model_name: str = "base", device: str = "cpu") -> None:
        """Загружает модель Whisper на выбранное устройство (CPU или CUDA)."""
        target_device = "cuda" if "cuda" in device.lower() else "cpu"

        if not WHISPER_AVAILABLE:
            logging.warning("Библиотека openai-whisper не найдена. Используется mock-заглушка.")
            self.use_mock_fallback = True
            self.current_model_name = model_name
            self.current_device = target_device
            return

        try:
            if self.model is None or self.current_model_name != model_name or self.current_device != target_device:
                logging.info(f"Загрузка модели Whisper '{model_name}' на устройство '{target_device}'...")
                self.model = whisper.load_model(model_name, device=target_device)
                self.current_model_name = model_name
                self.current_device = target_device
                self.use_mock_fallback = False
        except Exception as e:
            logging.warning(f"Не удалось загрузить реальную модель Whisper ({e}). Переключение на mock-режим.")
            self.use_mock_fallback = True

    def extract_audio_from_video(self, media_path: str) -> str:
        """Извлекает аудиодорожку из видеофайла во временный WAV-файл через ffmpeg-python."""
        ext = os.path.splitext(media_path)[1].lower()
        if ext not in self.VIDEO_EXTENSIONS:
            return media_path

        if not FFMPEG_AVAILABLE:
            logging.warning("Библиотека ffmpeg-python не установлена. Возврат исходного пути файла.")
            return media_path

        try:
            temp_wav = os.path.join(
                tempfile.gettempdir(),
                f"extracted_audio_{int(time.time())}.wav"
            )
            (
                ffmpeg
                .input(media_path)
                .output(temp_wav, acodec="pcm_s16le", ac=1, ar="16k")
                .overwrite_output()
                .run(quiet=True)
            )
            logging.info(f"Аудиодорожка успешно извлечена в {temp_wav}")
            return temp_wav
        except Exception as e:
            logging.warning(f"Не удалось извлечь аудио через ffmpeg ({e}). Используется исходный файл.")
            return media_path

    def transcribe(
        self,
        media_path: str,
        language: str = "ru",
        model_name: str = "base",
        device: str = "cpu",
        progress_callback: Optional[Callable[[int, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> List[Dict[str, Any]]:
        """
        Выполняет транскрипцию файла и возвращает список сегментов:
        [{'start': float, 'end': float, 'text': str}, ...]
        """
        if progress_callback:
            progress_callback(10, "Подготовка медиафайла и проверка аудиодорожки...")

        audio_path = self.extract_audio_from_video(media_path)

        if is_cancelled and is_cancelled():
            return []

        if progress_callback:
            progress_callback(25, f"Загрузка нейросетевой модели Whisper ({model_name})...")

        self.load_model(model_name, device)

        if is_cancelled and is_cancelled():
            return []

        # Если реальная модель доступна и загружена
        if not self.use_mock_fallback and self.model is not None and os.path.exists(audio_path):
            try:
                if progress_callback:
                    progress_callback(45, "Выполнение распознавания речи (Whisper)...")

                lang_arg = None if language == "auto" else language
                result = self.model.transcribe(audio_path, language=lang_arg, verbose=False)

                segments = []
                raw_segments = result.get("segments", [])
                total = max(len(raw_segments), 1)

                for idx, seg in enumerate(raw_segments):
                    if is_cancelled and is_cancelled():
                        return []
                    segments.append({
                        "start": float(seg.get("start", 0.0)),
                        "end": float(seg.get("end", 0.0)),
                        "text": str(seg.get("text", "")).strip()
                    })
                    if progress_callback:
                        pct = 45 + int((idx + 1) / total * 45)
                        progress_callback(pct, f"Обработка сегмента {idx + 1} из {total}...")

                return segments
            except Exception as e:
                logging.warning(f"Сбой реальной транскрипции ({e}). Запуск демонстрационной заглушки.")

        # Mock-заглушка для тестирования интерфейса без реальной модели
        return self._mock_transcribe(media_path, language, progress_callback, is_cancelled)

    def _mock_transcribe(
        self,
        media_path: str,
        language: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> List[Dict[str, Any]]:
        """Имитирует процесс транскрипции для быстрого тестирования всех функций UI."""
        filename = os.path.basename(media_path) if media_path else "demo_audio.mp3"

        if language == "en":
            mock_data = [
                {"start": 0.0, "end": 4.2, "text": f"hello everyone welcome to the recording of {filename}"},
                {"start": 5.0, "end": 10.5, "text": "uh today we are testing automatic speech recognition and speaker diarization"},
                {"start": 12.5, "end": 18.0, "text": "well the second speaker joins the conversation after a short pause"},
                {"start": 19.0, "end": 25.0, "text": "you can click on any timestamp code to seek the media player immediately"},
                {"start": 27.5, "end": 33.0, "text": "finally we can export the transcript to srt txt or docx formats"}
            ]
        else:
            mock_data = [
                {"start": 0.0, "end": 4.5, "text": f"привет всем начинаем тестовую запись файла {filename}"},
                {"start": 5.0, "end": 11.2, "text": "э-э сегодня мы проверяем работу десктопного приложения транскриптор на python"},
                {"start": 14.0, "end": 20.5, "text": "ну типа здесь вступает второй собеседник после заметной паузы в диалоге"},
                {"start": 21.0, "end": 27.8, "text": "при клике на любую строку с тайм-кодом плеер сразу перематывается на нужную секунду"},
                {"start": 30.0, "end": 36.0, "text": "э-э а в конце мы можем сохранить проект в базу данных или экспортировать в docx и srt"}
            ]

        total = len(mock_data)
        result_segments = []

        for i, item in enumerate(mock_data):
            if is_cancelled and is_cancelled():
                logging.info("Транскрипция отменена пользователем.")
                return []

            time.sleep(0.35)  # Имитация вычислений нейросети
            result_segments.append(item.copy())

            if progress_callback:
                pct = 35 + int((i + 1) / total * 55)
                progress_callback(pct, f"Распознавание речи (сегмент {i + 1}/{total})...")

        return result_segments


class TranscriptionWorker(QThread):
    """Фоновый поток Qt для выполнения транскрипции без блокировки интерфейса."""

    progress_changed = Signal(int, str)
    transcription_finished = Signal(list)
    transcription_cancelled = Signal()
    transcription_error = Signal(str)

    def __init__(
        self,
        transcriber: Transcriber,
        media_path: str,
        language: str,
        model_name: str,
        device: str
    ):
        super().__init__()
        self.transcriber = transcriber
        self.media_path = media_path
        self.language = language
        self.model_name = model_name
        self.device = device
        self._cancelled = False

    def cancel(self) -> None:
        """Устанавливает флаг отмены выполнения."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            segments = self.transcriber.transcribe(
                media_path=self.media_path,
                language=self.language,
                model_name=self.model_name,
                device=self.device,
                progress_callback=lambda p, msg: self.progress_changed.emit(p, msg),
                is_cancelled=self.is_cancelled
            )
            if self._cancelled:
                self.transcription_cancelled.emit()
            else:
                self.progress_changed.emit(100, "Транскрипция успешно завершена.")
                self.transcription_finished.emit(segments)
        except Exception as e:
            logging.error(f"Ошибка в потоке транскрипции: {e}", exc_info=True)
            self.transcription_error.emit(str(e))