from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt
from PySide6.QtWidgets import QApplication

import silverstar_flp
from silverstar_flp.app.version import PRODUCT_NAME, __version__
from silverstar_flp.export import service as export_service
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow


def _Logging_Configure() -> Path:
    data_directory = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    )
    data_directory.mkdir(parents=True, exist_ok=True)
    log_path = data_directory / "silverstar_flp.log"
    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return log_path


def _Arguments_Parse(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SilverStar Flight Log Processor GUI")
    parser.add_argument("path", nargs="?", type=Path, help="SSLOG0 BIN or .ssflp project")
    decoder_group = parser.add_mutually_exclusive_group()
    decoder_group.add_argument("--decoder", type=Path, help="exact .ssdecoder package")
    decoder_group.add_argument(
        "--auto-find",
        action="store_true",
        help="bounded search for one exact log/package pair",
    )
    parser.add_argument("--lang", choices=("zh_CN", "en_US"))
    parser.add_argument("--theme", choices=("light", "dark"))
    parser.add_argument("--version", action="version", version=__version__)
    options = parser.parse_args(arguments)
    if options.path is None and (options.decoder is not None or options.auto_find):
        parser.error("--decoder/--auto-find requires a log path")
    if (
        options.path is not None
        and options.path.suffix.casefold() == ".ssflp"
        and (options.decoder is not None or options.auto_find)
    ):
        parser.error("a project carries its own decoder identity")
    return options


def _RuntimeDiagnostics_Log() -> None:
    package_file = Path(silverstar_flp.__file__ or "").resolve()
    export_service_file = Path(export_service.__file__ or "").resolve()
    logging.info("SilverStar_FLP version=%s", __version__)
    logging.info("Python executable=%s", Path(sys.executable).resolve())
    logging.info("silverstar_flp package path=%s", package_file.parent)
    logging.info("export.service path=%s", export_service_file)


def main(arguments: list[str] | None = None) -> int:
    options = _Arguments_Parse(list(arguments) if arguments is not None else sys.argv[1:])
    QApplication.setOrganizationName("SilverStar")
    QApplication.setApplicationName(PRODUCT_NAME)
    QApplication.setApplicationVersion(__version__)
    application = QApplication([sys.argv[0]])
    application.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, False)
    log_path = _Logging_Configure()
    _RuntimeDiagnostics_Log()

    def exception_hook(exception_type, exception, exception_traceback) -> None:
        logging.critical(
            "Unhandled exception",
            exc_info=(exception_type, exception, exception_traceback),
        )
        sys.__excepthook__(exception_type, exception, exception_traceback)

    sys.excepthook = exception_hook
    settings = QSettings("SilverStar", "SilverStar_FLP")
    language = options.lang or str(settings.value("language", "zh_CN"))
    theme = options.theme or str(settings.value("theme", "light"))
    initial_path = options.path
    window = MainWindow(
        builtin_registry(),
        language=language,
        theme=theme,
        initial_path=initial_path,
        initial_decoder_path=options.decoder,
        initial_auto_find=bool(options.auto_find),
    )
    window.show()
    logging.info("%s %s started; log=%s", PRODUCT_NAME, __version__, log_path)
    return int(application.exec())
