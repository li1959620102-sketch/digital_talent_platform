"""
同步上下文中运行 async 协程的工具函数
LangGraph 0.2.x 节点均为同步函数，但 MilvusService / ResumeParser 使用 async def。
使用 asyncio.run() 在子线程中执行，避免 RuntimeError: no running event loop。
"""
import asyncio
import concurrent.futures
from typing import Any, Callable, Optional
import logging

logger = logging.getLogger(__name__)

# 复用固定线程池，避免频繁创建销毁
_thread_pool: Optional[concurrent.futures.ThreadPoolExecutor] = None


def _get_pool() -> concurrent.futures.ThreadPoolExecutor:
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="async_runner")
    return _thread_pool


def run_async(coro) -> Any:
    """
    在同步函数中运行 async 协程。
    自动检测是否已在事件循环中：
      - 已有时 loop → 用 thread pool 避免阻塞
      - 无 loop（LangGraph 同步节点）→ asyncio.run()
    """
    try:
        loop = asyncio.get_running_loop()
        # 已在事件循环中，提交到线程池执行
        future = _get_pool().submit(asyncio.run, coro)
        return future.result(timeout=60)
    except RuntimeError:
        # 无运行中事件循环，直接 run
        return asyncio.run(coro)


def run_async_no_wait(coro) -> concurrent.futures.Future:
    """不等待，立即提交到线程池（用于可延迟的 IO）"""
    return _get_pool().submit(asyncio.run, coro)
