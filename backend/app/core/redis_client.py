"""
Redis客户端管理
"""
import asyncio
import redis.asyncio as aioredis
from typing import Optional, Any
import logging
import json

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis客户端实例
redis_client: Optional[aioredis.Redis] = None


async def init_redis():
    """初始化Redis连接（带重试与降级，不阻塞应用启动）"""
    global redis_client

    last_err = None
    for attempt in range(3):
        try:
            redis_client = await aioredis.from_url(
                settings.REDIS_URI,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                decode_responses=True
            )
            await redis_client.ping()
            logger.info(f"✅ Redis连接成功（第 {attempt + 1} 次尝试）")
            return
        except Exception as e:
            last_err = e
            logger.warning(f"⚠️ Redis连接第 {attempt + 1} 次失败: {e}")
            # 关闭失败的连接再重试
            try:
                if redis_client:
                    await redis_client.close()
                    redis_client = None
            except Exception:
                pass
            await asyncio.sleep(1 + attempt)

    # 3 次重试后仍失败 → 降级为 None（不阻塞应用启动）
    logger.error(f"❌ Redis 连接失败（已重试 3 次）: {last_err}。Redis 相关功能将不可用，应用继续启动。")
    redis_client = None


async def close_redis():
    """关闭Redis连接"""
    global redis_client
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis连接已关闭")


async def get_redis() -> aioredis.Redis:
    """获取Redis客户端"""
    if not redis_client:
        raise RuntimeError("Redis客户端未初始化")
    return redis_client


class RedisService:
    """Redis服务封装"""
    
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
    
    async def get(self, key: str) -> Optional[Any]:
        """获取值"""
        value = await self.redis.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        expire: Optional[int] = None
    ) -> bool:
        """设置值"""
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        
        if expire:
            return await self.redis.setex(key, expire, value)
        return await self.redis.set(key, value)
    
    async def delete(self, key: str) -> int:
        """删除键"""
        return await self.redis.delete(key)
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return await self.redis.exists(key) > 0
    
    async def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间"""
        return await self.redis.expire(key, seconds)
    
    async def ttl(self, key: str) -> int:
        """获取剩余过期时间"""
        return await self.redis.ttl(key)
    
    async def incr(self, key: str) -> int:
        """自增"""
        return await self.redis.incr(key)
    
    async def decr(self, key: str) -> int:
        """自减"""
        return await self.redis.decr(key)
    
    async def hset(
        self, 
        name: str, 
        key: str, 
        value: Any
    ) -> int:
        """哈希表设置"""
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        return await self.redis.hset(name, key, value)
    
    async def hget(self, name: str, key: str) -> Optional[Any]:
        """哈希表获取"""
        value = await self.redis.hget(name, key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    
    async def hgetall(self, name: str) -> dict:
        """哈希表获取所有"""
        return await self.redis.hgetall(name)
    
    async def hdel(self, name: str, key: str) -> int:
        """哈希表删除"""
        return await self.redis.hdel(name, key)
    
    async def lpush(self, name: str, value: Any) -> int:
        """列表左侧插入"""
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        return await self.redis.lpush(name, value)
    
    async def rpush(self, name: str, value: Any) -> int:
        """列表右侧插入"""
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        return await self.redis.rpush(name, value)
    
    async def lpop(self, name: str) -> Optional[Any]:
        """列表左侧弹出"""
        value = await self.redis.lpop(name)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    
    async def rpop(self, name: str) -> Optional[Any]:
        """列表右侧弹出"""
        value = await self.redis.rpop(name)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    
    async def llen(self, name: str) -> int:
        """列表长度"""
        return await self.redis.llen(name)
    
    async def lrange(self, name: str, start: int, end: int) -> list:
        """列表范围获取"""
        return await self.redis.lrange(name, start, end)
    
    async def sadd(self, name: str, *values) -> int:
        """集合添加"""
        return await self.redis.sadd(name, *values)
    
    async def smembers(self, name: str) -> set:
        """集合获取所有成员"""
        return await self.redis.smembers(name)
    
    async def sismember(self, name: str, value: Any) -> bool:
        """检查是否是集合成员"""
        return await self.redis.sismember(name, value)
    
    async def srem(self, name: str, *values) -> int:
        """集合删除"""
        return await self.redis.srem(name, *values)
