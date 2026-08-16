class SinanError(Exception):
    """业务异常基类。code 为 HTTP 状态码。"""

    def __init__(
        self,
        message: str = "",
        code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: dict | None = None,
    ):
        self.message = message
        self.code = code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(SinanError):
    def __init__(self, message: str = "认证失败", details: dict | None = None):
        super().__init__(message, code=401, error_code="AUTHENTICATION_ERROR", details=details)


class AuthorizationError(SinanError):
    def __init__(self, message: str = "无权访问", details: dict | None = None):
        super().__init__(message, code=403, error_code="AUTHORIZATION_ERROR", details=details)


class NotFoundError(SinanError):
    def __init__(self, message: str = "资源不存在", details: dict | None = None):
        super().__init__(message, code=404, error_code="NOT_FOUND", details=details)


class GenerationError(SinanError):
    def __init__(self, message: str = "生成失败", details: dict | None = None):
        super().__init__(message, code=500, error_code="GENERATION_ERROR", details=details)


class JobConflictError(SinanError):
    def __init__(self, message: str = "任务冲突", details: dict | None = None):
        super().__init__(message, code=409, error_code="JOB_CONFLICT", details=details)