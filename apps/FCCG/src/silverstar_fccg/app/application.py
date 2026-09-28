from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from silverstar_fccg.app.version import PRODUCT_NAME, __version__
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.message_box import MessageBoxButtons_Localize


def WorkspaceRoot_Get() -> Path:
    return Path(__file__).resolve().parents[3]


def _Arguments_Parse(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SilverStar Flight Controller Code Generator"
    )
    parser.add_argument("--lang", choices=("zh_CN", "en_US"))
    parser.add_argument("--theme", choices=("light", "dark"))
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args(arguments)


def _Logging_Configure(workspace_root: Path) -> Path:
    log_directory = workspace_root / ".fccg" / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / "silverstar_fccg.log"
    handler = RotatingFileHandler(
        log_path,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    return log_path


def main(arguments: list[str] | None = None) -> int:
    options = _Arguments_Parse(list(arguments) if arguments is not None else sys.argv[1:])
    application = QApplication([sys.argv[0]])
    application.setOrganizationName("SilverStar")
    application.setApplicationName(PRODUCT_NAME)
    application.setApplicationVersion(__version__)
    application.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, False)
    workspace_root = WorkspaceRoot_Get()
    log_path = _Logging_Configure(workspace_root)
    settings = SettingsStore(workspace_root / ".fccg" / "settings.ini")
    language = options.lang or str(settings.Value_Get("language", "zh_CN"))
    theme = options.theme or str(settings.Value_Get("theme", "light"))
    translator = Translator(language)

    def exception_hook(exception_type, exception, exception_traceback) -> None:
        logging.critical(
            "Unhandled exception",
            exc_info=(exception_type, exception, exception_traceback),
        )
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(PRODUCT_NAME)
        box.setText(translator.Text_Get("error.unhandled_exception"))
        box.setDetailedText(str(exception))
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        MessageBoxButtons_Localize(box, translator)
        box.exec()

    sys.excepthook = exception_hook
    try:
        service = FccgService(workspace_root)
        window = MainWindow(settings, service=service, language=language, theme=theme)
    except Exception:
        logging.exception("Application startup failed")
        exception_type, exception, exception_traceback = sys.exc_info()
        assert exception_type is not None and exception is not None
        exception_hook(exception_type, exception, exception_traceback)
        return 1
    window.show()
    logging.info("%s %s started; log=%s", PRODUCT_NAME, __version__, log_path)
    return int(application.exec())
