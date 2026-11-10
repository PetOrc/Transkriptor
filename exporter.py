# exporter.py
import re
import logging
from typing import List, Tuple

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False


class Exporter:
    """Класс для экспорта транскрипции в форматы SRT, TXT и DOCX."""

    LINE_PATTERN = re.compile(r"^\[(\d{6})\]\s*(?:\[([^\]]+)\]\s*)?(.*)$")

    def export(self, text: str, output_path: str, fmt: str, media_duration: float = 0.0) -> None:
        """Универсальный метод вызова экспорта по выбранному формату."""
        fmt_upper = fmt.upper().strip()
        if fmt_upper == "SRT":
            self.export_srt(text, output_path, media_duration)
        elif fmt_upper == "TXT":
            self.export_txt(text, output_path)
        elif fmt_upper == "DOCX":
            self.export_docx(text, output_path)
        else:
            raise ValueError(f"Неподдерживаемый формат экспорта: {fmt}")

    def export_txt(self, text: str, output_path: str) -> None:
        """Экспортирует транскрипцию в текстовый файл UTF-8."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        logging.info(f"Экспорт в TXT выполнен: {output_path}")

    def export_srt(self, text: str, output_path: str, media_duration: float = 0.0) -> None:
        """Формирует валидный файл субтитров SRT на основе тайм-кодов из текста."""
        parsed = self._parse_lines(text)
        srt_blocks: List[str] = []

        for idx, (start_sec, speaker, content) in enumerate(parsed):
            # Определяем время окончания по началу следующей реплики или +4 сек
            if idx + 1 < len(parsed) and parsed[idx + 1][0] > start_sec:
                end_sec = parsed[idx + 1][0]
            elif media_duration > start_sec:
                end_sec = int(media_duration)
            else:
                end_sec = start_sec + 4

            if end_sec <= start_sec:
                end_sec = start_sec + 1

            start_srt = self._seconds_to_srt_time(start_sec)
            end_srt = self._seconds_to_srt_time(end_sec)
            display_text = f"[{speaker}] {content}" if speaker else content

            block = f"{idx + 1}\n{start_srt} --> {end_srt}\n{display_text}\n"
            srt_blocks.append(block)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_blocks))

        logging.info(f"Экспорт в SRT выполнен: {output_path}")

    def export_docx(self, text: str, output_path: str) -> None:
        """Экспортирует транскрипцию в документ Word (.docx) с помощью python-docx."""
        if not DOCX_AVAILABLE:
            raise RuntimeError(
                "Библиотека python-docx не установлена. Установите её командой: pip install python-docx"
            )

        doc = Document()
        doc.add_heading("Транскрипция аудио/видео записи", level=1)

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            doc.add_paragraph(stripped)

        doc.save(output_path)
        logging.info(f"Экспорт в DOCX выполнен: {output_path}")

    def _parse_lines(self, text: str) -> List[Tuple[int, str, str]]:
        """Разбирает строки текста на кортежи (секунды, спикер, текст)."""
        results: List[Tuple[int, str, str]] = []
        fallback_sec = 0

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            match = self.LINE_PATTERN.match(stripped)
            if match:
                ts_raw, speaker, content = match.groups()
                sec = int(ts_raw[:2]) * 3600 + int(ts_raw[2:4]) * 60 + int(ts_raw[4:6])
                results.append((sec, speaker or "", content.strip()))
                fallback_sec = sec + 4
            else:
                results.append((fallback_sec, "", stripped))
                fallback_sec += 4

        return results

    @staticmethod
    def _seconds_to_srt_time(seconds: int) -> str:
        """Переводит секунды в формат времени SRT: ЧЧ:ММ:СС,000."""
        hrs = seconds // 3600
        mins = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hrs:02d}:{mins:02d}:{secs:02d},000"