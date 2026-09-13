import os

import redis.asyncio as aredis

from util.env import Env

class RedisDB(object):
    _instance = None

    def __init__(self):
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls) -> 'RedisDB':
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls.redis = None
        return cls._instance

    @classmethod
    async def close(cls):
        if hasattr(cls, 'redis') and cls.redis is not None:
            await cls.redis.aclose()
        if cls._instance is not None:
            cls._instance = None

    @classmethod
    async def get_redis(cls) -> aredis.Redis:
        if cls.redis is not None:
            return cls.redis
        cls.redis = aredis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=6379,
            db=int(os.getenv('REDIS_DB', '1')),
            decode_responses=True,
            max_connections=5
        )
        return cls.redis

    async def pubsub(self) -> aredis.client.PubSub:
        redis = await self.get_redis()
        return redis.pubsub()

    async def set(self, key: str, value: str, expires: int = 0):
        # Key prefix keeps this bot friendly with other bots in the same redis DB
        key = f"{Env.currency_name().lower()}{key}"
        redis = await self.get_redis()
        await redis.set(key, value, ex=expires if expires else None)

    async def get(self, key: str):
        key = f"{Env.currency_name().lower()}{key}"
        redis = await self.get_redis()
        return await redis.get(key)

    async def delete(self, key: str):
        key = f"{Env.currency_name().lower()}{key}"
        await self._delete(key)

    async def _delete(self, key: str):
        redis = await self.get_redis()
        await redis.delete(key)

    async def exists(self, key: str):
        key = f"{Env.currency_name().lower()}{key}"
        redis = await self.get_redis()
        return (await redis.get(key)) is not None

    async def pause(self):
        key = f"{Env.currency_name().lower()}:botpaused"
        redis = await self.get_redis()
        await redis.set(key, "paused")

    async def resume(self):
        key = f"{Env.currency_name().lower()}:botpaused"
        await self._delete(key)

    async def is_paused(self) -> bool:
        key = f"{Env.currency_name().lower()}:botpaused"
        redis = await self.get_redis()
        return (await redis.get(key)) is not None
