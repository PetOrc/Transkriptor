# postprocessing.py
import re
import logging
from typing import List

try:
    import simplemma
    SIMPLEMMA_AVAILABLE = True
except ImportError:
    SIMPLEMMA_AVAILABLE = False


class PostProcessor:
    """Класс для постобработки текста: пунктуация, удаление слов-паразитов и форматирование."""

    # Слова-паразиты и междометия для фильтрации
    FILLER_PATTERNS = [
        r"\bэ+[-—]?э+\b",
        r"\bм+[-—]?м+\b",
        r"\bа+[-—]?а+\b",
        r"\bну\b",
        r"\bтипа\b",
        r"\bкороче\b",
        r"\bкак бы\b",
        r"\bтак сказать\b",
        r"\bв общем-то\b",
        r"\bзнаешь\b",
        r"\buh+\b",
        r"\bum+\b"
    ]

    # Союзы, перед которыми в русском языке ставится запятая
    COMMA_CONJUNCTIONS_RU = {"а", "но", "что", "чтобы", "потому", "поэтому", "однако", "когда", "если", "который"}
    QUESTION_WORDS_RU = {"кто", "что", "где", "когда", "почему", "зачем", "как", "сколько", "какой", "чей"}

    def __init__(self):
        self.filler_regex = re.compile(
            "|".join(self.FILLER_PATTERNS),
            flags=re.IGNORECASE
        )

    def remove_filler_words(self, text: str) -> str:
        """Удаляет слова-паразиты («э-э», «ну», «типа» и др.) с сохранением структуры тайм-кодов."""
        lines = text.splitlines()
        cleaned_lines: List[str] = []

        for line in lines:
            if not line.strip():
                cleaned_lines.append("")
                continue

            prefix, body = self._split_prefix_and_body(line)
            body = self.filler_regex.sub("", body)
            # Убираем двойные пробелы и лишние запятые после удаления слов
            body = re.sub(r"\s{2,}", " ", body).strip()
            body = re.sub(r"^[,.\s]+", "", body).strip()

            cleaned_lines.append(f"{prefix}{body}" if prefix else body)

        logging.info("Фильтрация слов-паразитов выполнена.")
        return "\n".join(cleaned_lines)

    def apply_smart_punctuation(self, text: str, lang: str = "ru") -> str:
        """Автоматически расставляет заглавные буквы, запятые и конечные знаки препинания."""
        lines = text.splitlines()
        processed_lines: List[str] = []
        norm_lang = "en" if lang == "en" else "ru"

        for line in lines:
            if not line.strip():
                processed_lines.append("")
                continue

            prefix, body = self._split_prefix_and_body(line)
            if not body:
                processed_lines.append(line)
                continue

            words = body.split()
            new_words: List[str] = []

            for i, word in enumerate(words):
                clean_w = re.sub(r"[^\w-]", "", word).lower()

                # Используем simplemma для нормализации при проверке союзов/местоимений
                lemma = clean_w
                if SIMPLEMMA_AVAILABLE and clean_w:
                    try:
                        lemma = simplemma.lemmatize(clean_w, lang=norm_lang).lower()
                    except Exception:
                        lemma = clean_w

                if i > 0 and (clean_w in self.COMMA_CONJUNCTIONS_RU or lemma in self.COMMA_CONJUNCTIONS_RU):
                    if not new_words[-1].endswith((",", ".", "!", "?", ":", ";")):
                        new_words[-1] = new_words[-1] + ","

                new_words.append(word)

            sentence = " ".join(new_words).strip()

            # Заглавная первая буква
            if sentence:
                sentence = sentence[0].upper() + sentence[1:]

            # Точка или вопросительный знак в конце строки
            first_word_clean = re.sub(r"[^\w]", "", words[0]).lower() if words else ""
            if sentence and not sentence.endswith((".", "!", "?", "…")):
                if first_word_clean in self.QUESTION_WORDS_RU:
                    sentence += "?"
                else:
                    sentence += "."

            processed_lines.append(f"{prefix}{sentence}" if prefix else sentence)

        logging.info("Умная пунктуация применена.")
        return "\n".join(processed_lines)

    def format_paragraphs_by_speaker(self, text: str) -> str:
        """Группирует и разбивает текст на абзацы при смене спикера."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""

        speaker_pattern = re.compile(r"^(?:\[\d{6}\]\s*)?\[([^\]]+)\]")
        formatted_lines: List[str] = []
        last_speaker = None

        for line in lines:
            match = speaker_pattern.match(line)
            current_speaker = match.group(1) if match else None

            if last_speaker is not None and current_speaker is not None and current_speaker != last_speaker:
                formatted_lines.append("")  # Пустая строка между разными спикерами

            formatted_lines.append(line)
            if current_speaker:
                last_speaker = current_speaker

        return "\n".join(formatted_lines)

    @staticmethod
    def _split_prefix_and_body(line: str):
        """Отделяет префикс тайм-кода и спикера ([000123] [Спикер 1]) от основного текста."""
        match = re.match(r"^((?:\[\d{6}\]\s*)?(?:\[[^\]]+\]\s*)?)(.*)$", line.strip())
        if match:
            return match.group(1), match.group(2)
        return "", line.strip()