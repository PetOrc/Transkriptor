# database.py
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any


class DatabaseManager:
    """Класс для управления базой данных SQLite проектов транскрипции."""

    def __init__(self, db_path: str = "transcriptor_projects.db"):
        self.db_path = db_path
        self.init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Создаёт подключение к базе данных с поддержкой внешних ключей."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_database(self) -> None:
        """Создаёт необходимые таблицы, если они ещё не существуют."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 1. Таблица проектов
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)

                # 2. Таблица медиафайлов
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS media_files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        type TEXT NOT NULL,
                        duration REAL DEFAULT 0.0,
                        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                    )
                """)

                # 3. Таблица настроек проекта
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        language TEXT DEFAULT 'ru',
                        model TEXT DEFAULT 'base',
                        diarization INTEGER DEFAULT 0,
                        punctuation INTEGER DEFAULT 1,
                        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                    )
                """)

                # 4. Таблица транскрипций
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS transcriptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        version INTEGER DEFAULT 1,
                        full_text TEXT DEFAULT '',
                        status TEXT DEFAULT 'created',
                        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                    )
                """)

                # 5. Таблица спикеров
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS speakers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        transcription_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        color TEXT NOT NULL,
                        FOREIGN KEY (transcription_id) REFERENCES transcriptions(id) ON DELETE CASCADE
                    )
                """)

                # 6. Таблица истории экспортов
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS exports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        format TEXT NOT NULL,
                        exported_at TEXT NOT NULL,
                        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                    )
                """)

                conn.commit()
                logging.info("База данных успешно инициализирована.")
        except Exception as e:
            logging.error(f"Ошибка инициализации БД: {e}", exc_info=True)
            raise

    def save_full_project(
        self,
        project_id: Optional[int],
        name: str,
        media_info: Dict[str, Any],
        settings_info: Dict[str, Any],
        transcription_text: str,
        status: str,
        speakers_list: List[Dict[str, str]]
    ) -> int:
        """Создаёт новый или обновляет существующий проект со всеми связанными данными."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if project_id is None:
                    cursor.execute(
                        "INSERT INTO projects (name, created_at) VALUES (?, ?)",
                        (name, now_str)
                    )
                    project_id = cursor.lastrowid
                else:
                    cursor.execute(
                        "UPDATE projects SET name = ? WHERE id = ?",
                        (name, project_id)
                    )

                # Сохранение медиафайла
                cursor.execute("DELETE FROM media_files WHERE project_id = ?", (project_id,))
                if media_info.get("path"):
                    cursor.execute(
                        """INSERT INTO media_files (project_id, path, type, duration)
                           VALUES (?, ?, ?, ?)""",
                        (
                            project_id,
                            media_info.get("path", ""),
                            media_info.get("type", "audio"),
                            float(media_info.get("duration", 0.0))
                        )
                    )

                # Сохранение настроек
                cursor.execute("DELETE FROM settings WHERE project_id = ?", (project_id,))
                cursor.execute(
                    """INSERT INTO settings (project_id, language, model, diarization, punctuation)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        project_id,
                        settings_info.get("language", "ru"),
                        settings_info.get("model", "base"),
                        int(bool(settings_info.get("diarization", False))),
                        int(bool(settings_info.get("punctuation", True)))
                    )
                )

                # Определение версии транскрипции
                cursor.execute(
                    "SELECT MAX(version) as max_ver FROM transcriptions WHERE project_id = ?",
                    (project_id,)
                )
                row = cursor.fetchone()
                next_version = (row["max_ver"] or 0) + 1

                cursor.execute(
                    """INSERT INTO transcriptions (project_id, version, full_text, status)
                       VALUES (?, ?, ?, ?)""",
                    (project_id, next_version, transcription_text, status)
                )
                transcription_id = cursor.lastrowid

                # Сохранение спикеров для текущей транскрипции
                for sp in speakers_list:
                    cursor.execute(
                        """INSERT INTO speakers (transcription_id, name, color)
                           VALUES (?, ?, ?)""",
                        (transcription_id, sp["name"], sp["color"])
                    )

                conn.commit()
                logging.info(f"Проект '{name}' (ID={project_id}) успешно сохранён.")
                return project_id
        except Exception as e:
            logging.error(f"Ошибка при сохранении проекта: {e}", exc_info=True)
            raise

    def log_export(self, project_id: int, path: str, fmt: str) -> None:
        """Записывает информацию о выполненном экспорте в таблицу exports."""
        try:
            with self._get_connection() as conn:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    """INSERT INTO exports (project_id, path, format, exported_at)
                       VALUES (?, ?, ?, ?)""",
                    (project_id, path, fmt, now_str)
                )
                conn.commit()
        except Exception as e:
            logging.error(f"Ошибка записи экспорта в БД: {e}", exc_info=True)

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Возвращает список всех сохранённых проектов."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, created_at FROM projects ORDER BY id DESC")
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Ошибка получения списка проектов: {e}", exc_info=True)
            return []

    def load_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Загружает полные данные проекта по его ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
                project = cursor.fetchone()
                if not project:
                    return None

                cursor.execute("SELECT * FROM media_files WHERE project_id = ?", (project_id,))
                media = cursor.fetchone()

                cursor.execute("SELECT * FROM settings WHERE project_id = ?", (project_id,))
                settings = cursor.fetchone()

                cursor.execute(
                    """SELECT * FROM transcriptions
                       WHERE project_id = ?
                       ORDER BY version DESC LIMIT 1""",
                    (project_id,)
                )
                transcription = cursor.fetchone()

                speakers = []
                if transcription:
                    cursor.execute(
                        "SELECT name, color FROM speakers WHERE transcription_id = ?",
                        (transcription["id"],)
                    )
                    speakers = [dict(r) for r in cursor.fetchall()]

                return {
                    "project": dict(project),
                    "media": dict(media) if media else None,
                    "settings": dict(settings) if settings else None,
                    "transcription": dict(transcription) if transcription else None,
                    "speakers": speakers
                }
        except Exception as e:
            logging.error(f"Ошибка загрузки проекта ID={project_id}: {e}", exc_info=True)
            raise