import datetime
import logging
import os
import sys

import termcolor

if os.name == "nt":  # Windows
    import colorama

    colorama.init()

from . import __appname__

COLORS = {
    "WARNING": "yellow",
    "INFO": "white",
    "DEBUG": "blue",
    "CRITICAL": "red",
    "ERROR": "red",
}


class ColoredFormatter(logging.Formatter):

    def __init__(self, fmt, use_color=True):
        logging.Formatter.__init__(self, fmt)
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        if self.use_color and levelname in COLORS:

            def colored(text):
                return termcolor.colored(
                    text,
                    color=COLORS[levelname],
                    attrs={"bold": True},
                )

            record.levelname2 = colored("{:<7}".format(record.levelname))
            record.message2 = colored(record.msg)

            asctime2 = datetime.datetime.fromtimestamp(record.created)
            record.asctime2 = termcolor.colored(asctime2, color="green")

            record.module2 = termcolor.colored(record.module, color="cyan")
            record.funcName2 = termcolor.colored(record.funcName, color="cyan")
            record.lineno2 = termcolor.colored(record.lineno, color="cyan")
        return logging.Formatter.format(self, record)


logger = logging.getLogger(__appname__)
logger.setLevel(logging.INFO)

stream_handler = logging.StreamHandler(sys.stderr)
handler_format = ColoredFormatter(
    "%(asctime)s [%(levelname2)s] %(module2)s:%(funcName2)s:%(lineno2)s"
    "- %(message2)s")
stream_handler.setFormatter(handler_format)

logger.addHandler(stream_handler)

# windows 平台
if os.name == "nt":
    log_path = fr'C:\dlcv\Lib\site-packages\dlcv_labelme_ai\{__appname__}.log'

    # 大于500MB
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if os.path.exists(log_path):
        if os.path.getsize(log_path) > 500 * 1024 * 1024:
            os.remove(log_path)

    file_handler = logging.FileHandler(log_path, mode="a")
    file_handler.setFormatter(handler_format)
    logger.addHandler(file_handler)


def _handle_exception(exc_type, exc_value, exc_traceback):
    import traceback
    from qtpy import QtWidgets

    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        sys.exit(0)

    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(True)

    traceback_str: str = "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.critical(traceback_str)

    traceback_html: str = traceback_str.replace("\n", "<br/>").replace(
        " ", "&nbsp;")
    QtWidgets.QMessageBox.critical(
        None,
        "Error",
        f"An unexpected error occurred. The application will close.<br/><br/>Please report issues following the <a href='https://labelme.io/docs/troubleshoot'>Troubleshoot</a>.<br/><br/>{traceback_html}",  # noqa: E501
    )

    app.quit()
    sys.exit(1)


sys.excepthook = _handle_exception
