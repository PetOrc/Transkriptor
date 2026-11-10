# main.py
import sys
import logging
from PySide6.QtWidgets import QApplication, QMessageBox
from main_window import MainWindow


def setup_logging() -> None:
    """Настраивает запись логов работы приложения в файл app.log."""
    logging.basicConfig(
        filename="app.log",
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8"
    )
    logging.info("Запуск приложения «Транскриптор».")


def main() -> None:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Транскриптор")

    try:
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        logging.critical(f"Критическая ошибка при запуске приложения: {e}", exc_info=True)
        QMessageBox.critical(None, "Критическая ошибка", f"Приложение завершилось с ошибкой:\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()