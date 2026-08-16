# sinan/services/cancel_registry.py
"""生成流取消登记：同实例用 asyncio.Event（零延迟），跨实例用带 TTL 的 Redis 键。"""
import asyncio

from sinan.services.redis import get_redis

# 内存中维护每个会话的取消开关，key 是 session_id，value 是 asyncio.Event
# asyncio.Event 是 Python 内置的"开关"：set() 打开，clear() 关闭，is_set() 查状态
_cancel_events: dict[str, asyncio.Event] = {}

# Redis 中取消标记的 key 前缀，完整 key 形如 "sinan:cancel:abc123"
_REDIS_PREFIX = "sinan:cancel:"

# Redis key 的过期时间（秒），防止异常情况下标记永久残留
_REDIS_TTL = 60  # 秒，远超单次生成流生命周期


"""
生成流的代码里大概是这样调用的：

  # 第一步：流开始前，把开关重置为"未取消"
  await cancel_registry.clear_async(session_id)

  # 第二步：每输出一个 token，就查一次开关
  async for token in llm.stream(prompt):
      if await cancel_registry.is_cancelled_async(session_id):
          break   # 开关是开的，停止生成
      yield token

  # 用户点"停止"时，另一个接口调用这个
  await cancel_registry.cancel_async(session_id)
  # 开关被打开，上面的循环下次检查时就会 break
  
asyncio.Event 的内部实现大概是这样的：
class Event:
      def __init__(self):
          self._flag = False   # 内部就是一个布尔值

      def set(self):
          self._flag = True    # 打开

      def clear(self):
          self._flag = False   # 关闭

      def is_set(self):
          return self._flag    # 查询
"""

def get_or_create(session_id: str) -> asyncio.Event:
    """获取指定会话的取消开关，若不存在则新建一个（默认关闭状态）。"""
    if session_id not in _cancel_events:
        _cancel_events[session_id] = asyncio.Event()
    return _cancel_events[session_id]


def cancel(session_id: str) -> None:
    """在内存中打开取消开关（同步版本，仅影响当前进程）。"""
    get_or_create(session_id).set()


async def cancel_async(session_id: str) -> None:
    """打开取消开关（异步版本）：同时写内存和 Redis，跨进程/实例可见。

    典型调用方：用户点击"停止生成"时的 HTTP 接口。
    Redis 写入失败时静默降级，内存标记仍有效，不影响本实例的取消检测。
    """
    cancel(session_id)
    try:
        await get_redis().set(f"{_REDIS_PREFIX}{session_id}", "1", ex=_REDIS_TTL)
    except Exception:
        pass  # 内存标记已置位；跨实例检测降级但不影响本实例


def clear(session_id: str) -> None:
    """在内存中关闭取消开关，重置为"未取消"状态（同步版本）。"""
    _cancel_events.setdefault(session_id, asyncio.Event()).clear()


async def clear_async(session_id: str) -> None:
    """关闭取消开关，重置为"未取消"状态（异步版本）：同时清除内存和 Redis。

    典型调用方：每次生成流开始前调用，防止上一次的取消状态残留。
    """
    clear(session_id)
    try:
        await get_redis().delete(f"{_REDIS_PREFIX}{session_id}")
    except Exception:
        pass


def is_cancelled(session_id: str) -> bool:
    """查询内存中的取消开关是否已打开（同步版本，仅查当前进程）。"""
    ev = _cancel_events.get(session_id)
    return ev is not None and ev.is_set()


async def is_cancelled_async(session_id: str) -> bool:
    """查询是否已被取消（异步版本）：先查内存（快），再查 Redis（慢）。

    典型调用方：生成循环中每输出一个 token 前调用一次。
    - 内存命中直接返回，避免网络开销
    - 内存未命中时查 Redis，支持跨实例取消感知
    - Redis 不可用时返回 False，绝不因基础设施故障误取消正常生成
    - 从 Redis 读到取消信号后回写内存，后续检查走快路径
    """
    if is_cancelled(session_id):
        return True
    try:
        exists = await get_redis().exists(f"{_REDIS_PREFIX}{session_id}")
    except Exception:
        return False
    if exists:
        cancel(session_id)  # 本地缓存，后续检查走快路径
    return bool(exists)