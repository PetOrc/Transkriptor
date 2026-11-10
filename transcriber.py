# transcriber.py
"""Распознавание речи в отдельном процессе с возможностью немедленной отмены."""
import os
import glob
import logging
import multiprocessing as mp
import queue
import tempfile
import uuid
from typing import List, Dict, Any, Optional
from PySide6.QtCore import QThread, Signal

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


def _resolve_model(model_name: str, model_path: str) -> str:
    """Возвращает путь к локальному checkpoint OpenAI Whisper либо имя встроенной модели."""
    if not model_path:
        return model_name
    path = os.path.abspath(os.path.expanduser(model_path))
    if os.path.isfile(path):
        if not path.lower().endswith(".pt"):
            raise ValueError(
                "Выбранный файл не является checkpoint-файлом OpenAI Whisper (.pt). "
                "Форматы CTranslate2/whisper.cpp из Subtitle Edit напрямую несовместимы."
            )
        return path
    if os.path.isdir(path):
        candidates = glob.glob(os.path.join(path, "*.pt"))
        if not candidates:
            raise FileNotFoundError(
                "В указанной папке не найден файл модели *.pt. "
                "Укажите checkpoint OpenAI Whisper или выберите стандартную модель для загрузки."
            )
        if len(candidates) > 1:
            names = ", ".join(os.path.basename(p) for p in candidates)
            raise ValueError(f"В папке несколько моделей ({names}). Укажите конкретный файл .pt.")
        return candidates[0]
    raise FileNotFoundError(f"Путь к локальной модели не существует: {path}")


def _transcribe_process(args, output_queue):
    """Дочерний процесс: тяжёлый вызов Whisper можно остановить terminate()."""
    media_path, language, model_name, device, model_path = args
    try:
        import whisper
        resolved_model = _resolve_model(model_name, model_path)
        output_queue.put(("progress", 8, "Загрузка локальной модели Whisper..."))
        model = whisper.load_model(resolved_model, device="cuda" if "cuda" in device.lower() else "cpu")
        output_queue.put(("progress", 20, "Подготовка аудио..."))
        source = media_path
        temp_audio = None
        ext = os.path.splitext(media_path)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            try:
                import ffmpeg
                temp_audio = os.path.join(tempfile.gettempdir(), f"transkriptor_{uuid.uuid4().hex}.wav")
                (
                    ffmpeg.input(media_path)
                    .output(temp_audio, acodec="pcm_s16le", ac=1, ar="16k")
                    .overwrite_output().run(quiet=True)
                )
                source = temp_audio
            except Exception as exc:
                raise RuntimeError(
                    "Не удалось извлечь аудио из видео. Проверьте установку ffmpeg "
                    f"и доступность видеодорожки: {exc}"
                ) from exc
        output_queue.put(("progress", 25, "Распознавание речи..."))
        result = model.transcribe(
            source,
            language=None if language == "auto" else language,
            verbose=False,
            fp16=("cuda" in device.lower())
        )
        segments = [
            {"start": float(s.get("start", 0)), "end": float(s.get("end", 0)),
             "text": str(s.get("text", "")).strip()}
            for s in result.get("segments", [])
        ]
        output_queue.put(("result", segments))
        if temp_audio and os.path.exists(temp_audio):
            os.remove(temp_audio)
    except Exception as exc:
        output_queue.put(("error", f"{type(exc).__name__}: {exc}"))


class Transcriber:
    """Хранит расширения медиа и разрешает локальные модели Whisper."""
    VIDEO_EXTENSIONS = VIDEO_EXTENSIONS
    AUDIO_EXTENSIONS = AUDIO_EXTENSIONS
    MEDIA_EXTENSIONS = MEDIA_EXTENSIONS

    def __init__(self):
        pass


class TranscriptionWorker(QThread):
    progress_changed = Signal(int, str)
    transcription_finished = Signal(list)
    transcription_cancelled = Signal()
    transcription_error = Signal(str)

    def __init__(self, transcriber, media_path, language, model_name, device, model_path=""):
        super().__init__()
        self.media_path = media_path
        self.language = language
        self.model_name = model_name
        self.device = device
        self.model_path = model_path
        self._cancelled = False
        self._process = None
        self._queue = None

    def cancel(self):
        self._cancelled = True
        # Процесс изолирован от GUI и модели: terminate прерывает даже зависший transcribe().
        if self._process is not None and self._process.is_alive():
            self._process.terminate()

    def run(self):
        if not self.media_path or not os.path.isfile(self.media_path):
            self.transcription_error.emit("Медиафайл не выбран или не существует.")
            return
        if os.path.splitext(self.media_path)[1].lower() not in MEDIA_EXTENSIONS:
            self.transcription_error.emit("Формат файла не поддерживается.")
            return
        ctx = mp.get_context("spawn")
        self._queue = ctx.Queue()
        self._process = ctx.Process(
            target=_transcribe_process,
            args=((self.media_path, self.language, self.model_name, self.device, self.model_path), self._queue)
        )
        try:
            self._process.start()
            while self._process.is_alive() or not self._queue.empty():
                if self._cancelled:
                    if self._process.is_alive():
                        self._process.terminate()
                    self._process.join(timeout=2)
                    self.transcription_cancelled.emit()
                    return
                try:
                    item = self._queue.get(timeout=0.15)
                except queue.Empty:
                    continue
                if item[0] == "progress":
                    self.progress_changed.emit(item[1], item[2])
                elif item[0] == "result":
                    self._result = item[1]
                elif item[0] == "error":
                    self._error = item[1]
            self._process.join()
            if self._cancelled:
                self.transcription_cancelled.emit()
            elif hasattr(self, "_error"):
                self.transcription_error.emit(self._error)
            elif hasattr(self, "_result"):
                self.progress_changed.emit(100, "Транскрипция завершена.")
                self.transcription_finished.emit(self._result)
            else:
                self.transcription_error.emit("Процесс распознавания завершился без результата.")
        except Exception as exc:
            logging.exception("Ошибка процесса транскрипции")
            self.transcription_error.emit(str(exc))
        finally:
            if self._queue is not None:
                self._queue.close()
