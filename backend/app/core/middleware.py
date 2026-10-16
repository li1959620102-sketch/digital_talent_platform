"""
中间件
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import time
import json

logger = logging.getLogger(__name__)


class RequestLogMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""
    
    async def dispatch(self, request: Request, call_next):
        # 记录请求开始时间
        start_time = time.time()
        
        # 记录请求信息
        request_id = id(request)
        method = request.method
        url = str(request.url)
        client_ip = request.client.host if request.client else "unknown"
        
        logger.info(
            f"▶️ 请求开始 [{request_id}] {method} {url} - 客户端: {client_ip}"
        )
        
        # 调用下一个中间件或路由处理器
        response: Response = await call_next(request)
        
        # 计算处理时间
        process_time = (time.time() - start_time) * 1000
        
        # 记录响应信息
        status_code = response.status_code
        status_emoji = "✅" if 200 <= status_code < 300 else "⚠️" if 300 <= status_code < 400 else "❌"
        
        logger.info(
            f"◀️ 请求完成 [{request_id}] {status_emoji} {status_code} - 耗时: {process_time:.2f}ms"
        )
        
        # 添加处理时间到响应头
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
        
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件"""
    
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        
        # 添加安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """简单的速率限制中间件"""
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts = {}  # 实际生产环境应使用Redis
    
    async def dispatch(self, request: Request, call_next):
        # 获取客户端IP
        client_ip = request.client.host if request.client else "unknown"
        
        # 检查是否需要限流（排除健康检查等端点）
        if request.url.path in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # 获取当前分钟的时间戳
        current_minute = int(time.time() / 60)
        
        # 构建键
        key = f"{client_ip}:{current_minute}"
        
        # 更新计数
        if key in self.request_counts:
            self.request_counts[key] += 1
        else:
            # 清理过期的键（保留最近2分钟）
            self.request_counts = {
                k: v for k, v in self.request_counts.items()
                if int(k.split(":")[1]) >= current_minute - 1
            }
            self.request_counts[key] = 1
        
        # 检查是否超限
        if self.request_counts[key] > self.requests_per_minute:
            logger.warning(f"⚠️ IP {client_ip} 触发速率限制")
            return Response(
                content=json.dumps({
                    "code": 429,
                    "message": "请求过于频繁，请稍后再试"
                }),
                status_code=429,
                media_type="application/json"
            )
        
        return await call_next(request)
