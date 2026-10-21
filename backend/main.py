"""
AI数字化人才平台 - FastAPI应用入口
"""
from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.middleware.gzip import GZipMiddleware  # 已移除：参考 large_health_reference 精简风格，由 Nginx gzip 替代
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import logging
from logging.handlers import RotatingFileHandler
import time
from pathlib import Path
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import (
    init_db,
    close_db,
    init_mysql_tables,
    get_mysql_engine,
    get_postgres_async_engine,
)
from app.core.redis_client import init_redis, close_redis
import app.core.redis_client as redis_module
from app.core.milvus_client import init_milvus
from app.core.postgresql import init_pgsql_tables
from app.core.seed import init_seed_data
from app.agents.agent_runtime import runtime as agent_runtime
from app.agents.dynamic_executor import build_recovery_runner
from app.api import api_router
from app.core.exceptions import AppException
# from app.core.middleware import RequestLogMiddleware  # 已移除：参考 large_health_reference 精简风格，由 uvicorn access_log 替代
# 参考架构复用：统一异常体系（新层）
from app.exceptions.base_api_exception import BaseAPIException, RAGException
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool


# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
import os as _os
import sys as _sys
from logging.handlers import RotatingFileHandler as _StdRotatingFileHandler


class _ShareDeleteRotatingFileHandler(_StdRotatingFileHandler):
    """多进程安全的 RotatingFileHandler（Windows）。

    背景：uvicorn 热重载(reload=True)会产生主进程+worker 多进程，若都用标准
    RotatingFileHandler 打开同一日志文件，则文件句柄默认不带 FILE_SHARE_DELETE，
    任一进程轮转(rename app.log -> app.log.1)时会抛 PermissionError: [WinError 32]
    "另一个程序正在使用此文件"。本类在打开文件时显式声明共享删除/读写权限，
    使多进程可共享同一日志文件并安全轮转。
    """
    if _sys.platform == "win32":
        def _open(self):
            import ctypes
            from ctypes import wintypes
            import msvcrt

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            GENERIC_READ = 0x80000000
            GENERIC_WRITE = 0x40000000
            # 共享标志：允许其它进程读/写/删除同一文件（关键：FILE_SHARE_DELETE）
            FILE_SHARE_READ = 0x1
            FILE_SHARE_WRITE = 0x2
            FILE_SHARE_DELETE = 0x4
            OPEN_ALWAYS = 4
            FILE_ATTRIBUTE_NORMAL = 0x80

            kernel32.CreateFileW.restype = wintypes.HANDLE
            kernel32.CreateFileW.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                wintypes.HANDLE,
            ]

            handle = kernel32.CreateFileW(
                self.baseFilename,
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                None, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, None,
            )
            if handle == wintypes.HANDLE(-1).value or not handle:
                raise OSError(ctypes.get_last_error(),
                              f"无法打开日志文件 {self.baseFilename}")
            # 把 Win32 句柄转成 CRT 文件描述符，再包成 file object
            fd = msvcrt.open_osfhandle(handle, _os.O_WRONLY | _os.O_APPEND)
            return _os.fdopen(fd, "a", encoding=self.encoding,
                              errors="backslashreplace")
    # 非 Windows 走标准实现
    else:
        _open = _StdRotatingFileHandler._open


# 配置日志（RotatingFileHandler 轮转：单文件 10MB，保留 5 个备份，避免无限增长）
# 注意：使用 _ShareDeleteRotatingFileHandler 而非标准 RotatingFileHandler，
# 以规避 uvicorn 热重载多进程下日志轮转的 PermissionError: [WinError 32]。
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        _ShareDeleteRotatingFileHandler(
            settings.LOG_FILE, maxBytes=10 * 1024 * 1024,
            backupCount=5, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("🚀 启动AI数字化人才平台...")
    
    # 创建必要的目录
    Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)
    
    # 初始化数据库连接
    init_db()
    logger.info("✅ 数据库连接初始化完成")

    # 初始化MySQL业务表（以 ORM 模型为准，补齐缺失表/列，幂等）
    init_mysql_tables()
    logger.info("✅ MySQL业务表初始化完成")
    
    # 初始化Redis连接
    await init_redis()
    logger.info("✅ Redis连接初始化完成")
    
    # 初始化Milvus向量库
    await init_milvus()
    logger.info("✅ Milvus向量库初始化完成")
    
    # 初始化PostgreSQL分析库（招标文件强制：PgSQL用于海量分析数据）
    init_pgsql_tables()
    logger.info("✅ PostgreSQL分析库初始化完成")

    # 初始化种子数据（默认组织 + 4 种角色 + 可选的环境变量初始超管账号）
    init_seed_data()
    logger.info("✅ 种子数据初始化完成（组织 + super_admin/admin/hr/user + 超管账号）")

    recovered = agent_runtime.recover_tasks(build_recovery_runner)
    logger.info("✅ Agent 任务恢复完成：恢复 %s 个可重建任务", recovered)

    logger.info(f"🎉 {settings.APP_NAME} v{settings.APP_VERSION} 启动成功!")
    
    yield
    
    # 关闭时清理
    logger.info("🛑 关闭AI数字化人才平台...")
    await close_db()
    await close_redis()
    logger.info("👋 应用已关闭")


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else None,
    redoc_url=f"{settings.API_V1_PREFIX}/redoc" if settings.DEBUG else None,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan
)


# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# GZip压缩（已移除：参考 large_health_reference 精简风格，由 Nginx gzip 模块替代）
# app.add_middleware(GZipMiddleware, minimum_size=1000)

# 请求日志中间件（已移除：参考 large_health_reference 精简风格，由 uvicorn access_log 替代）
# app.add_middleware(RequestLogMiddleware)


# 挂载静态文件
if settings.DEBUG and Path(settings.MEDIA_ROOT).exists():
    app.mount(settings.MEDIA_URL, StaticFiles(directory=settings.MEDIA_ROOT), name="media")


# 注册路由
app.include_router(api_router, prefix=settings.API_PREFIX)


# 全局异常处理
# ── 新层：BaseAPIException（参考架构，HTTPException 继承，标准 {code, message} 响应）
@app.exception_handler(BaseAPIException)
async def base_api_exception_handler(request: Request, exc: BaseAPIException):
    """捕获所有 BaseAPIException 派生异常，参考 large_health_reference 统一响应格式。"""
    extra = getattr(exc, "extra", None)
    logger.error(
        f"[BaseAPI {exc.code}] {exc.detail}",
        extra={"code": exc.code, "extra": extra},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.detail,
            "details": extra,
        },
    )


# ── 新层：RAGException（轻量域异常 → 转为 500）
@app.exception_handler(RAGException)
async def rag_exception_handler(request: Request, exc: RAGException):
    """捕获轻量域异常，RAGException → 通用 500 响应。"""
    logger.error(f"[RAGException {exc.code}] {exc.message}", exc_info=False)
    return JSONResponse(
        status_code=500,
        content={"code": exc.code, "message": exc.message},
    )


# ── 旧层：AppException（向后兼容）
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """自定义异常处理"""
    logger.error(f"应用异常: {exc.message}", extra={"code": exc.code, "details": exc.details})
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理。

    安全原则：堆栈与内部细节只进日志，绝不回传客户端（无论 DEBUG 与否），
    避免泄露框架路径/表结构/内部实现给外部探测者。
    """
    logger.error(f"未处理的异常: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "details": None
        }
    )


# 健康检查
@app.get("/health", tags=["健康检查"])
async def health_check():
    """进程存活探针；不检查外部依赖。"""
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


@app.get("/health/ready", tags=["健康检查"])
async def readiness_check(strict: bool = Query(False, description="严格检查向量库、对象存储和模型服务")):
    """生产就绪探针；strict=true 时检查完整 AI 依赖链。"""
    checks = {"mysql": False, "postgres": False, "redis": False}

    try:
        mysql_engine = get_mysql_engine()
        if mysql_engine is not None:
            def _ping_mysql():
                with mysql_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            await run_in_threadpool(_ping_mysql)
            checks["mysql"] = True
    except Exception as exc:
        logger.warning(f"就绪检查 MySQL 失败: {exc}")

    try:
        postgres_engine = get_postgres_async_engine()
        if postgres_engine is not None:
            async with postgres_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["postgres"] = True
    except Exception as exc:
        logger.warning(f"就绪检查 PostgreSQL 失败: {exc}")

    try:
        if redis_module.redis_client is not None:
            checks["redis"] = bool(await redis_module.redis_client.ping())
    except Exception as exc:
        logger.warning(f"就绪检查 Redis 失败: {exc}")

    if strict:
        checks.update({"milvus": False, "minio": False, "llm": False})
        try:
            from pymilvus import connections, utility
            if not connections.has_connection(settings.MILVUS_ALIAS):
                connections.connect(
                    alias=settings.MILVUS_ALIAS,
                    host=settings.MILVUS_HOST,
                    port=settings.MILVUS_PORT,
                    user=settings.MILVUS_USER or None,
                    password=settings.MILVUS_PASSWORD or None,
                )
            checks["milvus"] = bool(utility.get_server_version(using=settings.MILVUS_ALIAS))
        except Exception as exc:
            logger.warning(f"就绪检查 Milvus 失败: {exc}")

        try:
            from minio import Minio
            endpoint = settings.MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
            client = Minio(endpoint, access_key=settings.MINIO_ACCESS_KEY,
                           secret_key=settings.MINIO_SECRET_KEY, secure=settings.MINIO_SECURE)
            await run_in_threadpool(client.list_buckets)
            checks["minio"] = True
        except Exception as exc:
            logger.warning(f"就绪检查 MinIO 失败: {exc}")

        try:
            import httpx
            base_url = settings.OLLAMA_BASE_URL.rstrip("/")
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(base_url + "/api/tags")
                checks["llm"] = response.status_code < 500
        except Exception as exc:
            logger.warning(f"就绪检查 LLM 失败: {exc}")

        if settings.DIFY_ENABLED:
            checks["dify"] = False
            try:
                import httpx
                async with httpx.AsyncClient(timeout=3) as client:
                    response = await client.get(settings.DIFY_API_BASE.rstrip("/") + "/health")
                    checks["dify"] = response.status_code < 500
            except Exception as exc:
                logger.warning(f"就绪检查 Dify 失败: {exc}")

    if not all(checks.values()):
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "strict": strict, "checks": checks},
        )
    return {"status": "ready", "strict": strict, "checks": checks}


# 根路径
@app.get("/", tags=["根路径"])
async def root():
    """根路径"""
    return {
        "message": f"欢迎使用{settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": f"{settings.API_PREFIX}/docs"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        reload=settings.DEBUG,
        reload_dirs=["app"],           # 仅监控 app 目录，避免日志触发循环重启
        reload_excludes=["*.log", "*.db", "*.sqlite"],
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
        timeout_keep_alive=settings.KEEP_ALIVE
    )
