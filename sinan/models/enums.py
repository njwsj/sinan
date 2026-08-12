from enum import Enum


class SessionStatus(str, Enum):
    PENDING = "pending"           # 已创建，等待处理
    RUNNING = "running"           # 流水线执行中
    COMPLETED = "completed"       # 成功完成，页面已生成
    FAILED = "failed"             # 执行失败，流程终止
    AWAITING_INPUT = "awaiting_input"  # 等待用户补充输入


class PageStatus(str, Enum):
    DRAFT = "draft"               # 草稿，生成中或未发布
    PUBLISHED = "published"       # 已发布，对外可访问
    ARCHIVED = "archived"         # 已归档，旧版本