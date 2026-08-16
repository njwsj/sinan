import logging
import logging.handlers
from pathlib import Path

from sinan.api.context import ContextLogFilter

# 项目根：.../sinan（仓库根），logs 放这里
_project_root = Path(__file__).resolve().parent.parent.parent
_log_dir = _project_root / "logs"


def setup_logging(debug: bool = False):
    _log_dir.mkdir(exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    log_filter = ContextLogFilter()

    # 业务日志 → sinan.log
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(_log_dir / "sinan.log"),
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] [%(trace_id)s] [%(user)s] %(message)s"
    ))
    file_handler.addFilter(log_filter)

    # 控制台
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(trace_id)s] [%(user)s] %(message)s"
    ))
    console_handler.addFilter(log_filter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [file_handler, console_handler]

    # 访问日志 → sinan-access.log（结构化，单独 logger，不向上传播）
    access_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(_log_dir / "sinan-access.log"),
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    access_handler.setLevel(logging.INFO)
    access_handler.setFormatter(logging.Formatter("%(message)s"))
    access_logger = logging.getLogger("sinan.access")
    access_logger.setLevel(logging.INFO)
    access_logger.handlers = [access_handler]
    access_logger.propagate = False