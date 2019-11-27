import aioredis
import asyncio

from util.env import Env

class RedisDB(object):
    _instance = None

    def __init__(self):
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls) -> 'RPCClient':
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
        return cls._instance

    @classmethod
    async def close(cls):
        if cls.redis is not None:
            await cls.redis.wait_closed()
        if cls._instance is not None:
            cls._instance = None

    @classmethod
    async def get_redis(cls) -> aioredis.Redis:
        if cls.redis is not None:
            return cls.redis
        # TODO - we should let them override redis host/port in configuration
        cls.redis = await aioredis.create_redis_pool(('localhost', 6379), db=1, encoding='utf-8', minsize=1, maxsize=5)

    async def set(self, key: str, value: str, expires: int = 0):
        """Basic redis SET"""
        # Add a prefix to allow our bot to be friendly with other bots within the same redis DB
        key = f"{Env.currency_name().lower()}{key}"
        redis = await self.get_redis()
        await redis.set(key, value, expire=expires)

    async def get(self, key: str):
        """Redis GET"""
        # Add a prefix to allow our bot to be friendly with other bots within the same redis DB
        key = f"{Env.currency_name().lower()}{key}"
        redis = await self.get_redis()
        await redis.get(key)