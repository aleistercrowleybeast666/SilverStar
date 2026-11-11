from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QRect, QSettings, QStandardPaths, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMainWindow

import silverstar_flp
from silverstar_flp.app.startup_error import StartupError_Report
from silverstar_flp.app.version import PRODUCT_NAME, __version__
from silverstar_flp.core.runtime import NumericalRuntime_Validate
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
    parser.add_argument("--decoder-search-dir", type=Path, action="append", default=[])
    options = parser.parse_args(arguments)
    if len(options.decoder_search_dir) > 4 or (options.decoder_search_dir and
            (options.path is None or options.decoder is not None or options.path.suffix.casefold() not in (".bin", ".sslog"))):
        parser.error("--decoder-search-dir requires a log and at most four directories for exact lookup")
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


def Application_ConstrainInitialGeometry(
    window: QMainWindow, available: QRect | None = None,
) -> None:
    """Keep the initial native frame on its screen without resetting valid geometry."""
    if window.isMaximized() or window.isFullScreen():
        return
    if available is None:
        screen = window.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
    frame = window.frameGeometry()
    if not available.isValid() or available.contains(frame):
        return
    border_width = max(0, frame.width() - window.width())
    border_height = max(0, frame.height() - window.height())
    width = max(1, available.width() - border_width)
    height = max(1, available.height() - border_height)
    window.setMinimumSize(min(window.minimumWidth(), width), min(window.minimumHeight(), height))
    window.resize(min(window.width(), width), min(window.height(), height))
    frame = window.frameGeometry()
    window.move(
        max(available.left(), min(frame.left(), available.right() - frame.width() + 1)),
        max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1)),
    )


def main(arguments: list[str] | None = None) -> int:
    options = _Arguments_Parse(list(arguments) if arguments is not None else sys.argv[1:])
    try:
        NumericalRuntime_Validate()
    except RuntimeError as error:
        language = options.lang or str(
            QSettings("SilverStar", "SilverStar_FLP").value("language", "zh_CN")
        )
        StartupError_Report(error, language)
        return 2
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
        initial_auto_find=options.auto_find or options.decoder is None,
        initial_decoder_roots=tuple(options.decoder_search_dir) or None,
    )
    window.show()
    Application_ConstrainInitialGeometry(window)
    # Native frame margins can settle after show; this is startup-only.
    QTimer.singleShot(0, window, lambda: Application_ConstrainInitialGeometry(window))
    logging.info("%s %s started; log=%s", PRODUCT_NAME, __version__, log_path)
    return int(application.exec())
