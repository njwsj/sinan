# -*- coding: UTF-8 -*-
"""请求上下文：用 contextvars 存 trace_id / 当前用户，配合 ContextLogFilter 注入日志。"""
import logging
import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")
request_user_var: ContextVar[str] = ContextVar("request_user", default="-")
session_id_var: ContextVar[str] = ContextVar("session_id", default="-")
job_id_var: ContextVar[str] = ContextVar("job_id", default="-")


def new_trace_id() -> str:
    """生成一个短随机 trace_id。"""
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    return trace_id_var.get()


def get_request_user() -> str:
    return request_user_var.get()


class ContextLogFilter(logging.Filter):
    """把 trace_id / user 注入到每条日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get()
        record.user = request_user_var.get()
        return True