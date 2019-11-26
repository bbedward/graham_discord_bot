import aioredis
import asyncio

class RedisDB(object):
    _instance = None

    def __init__(self):
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls) -> 'RPCClient':
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            # TODO - we should let them override redis host/port in configuration
            try:
                cls.redis = asyncio.get_event_loop().run_until_complete(aioredis.create_redis_pool(('localhost', 6379), db=1, encoding='utf-8', minsize=1, maxsize=5))
            except Exception:
                raise Exception("Could not connect to redis at localhost:6379")
        return cls._instance

    @classmethod
    async def close(cls):
        if cls.redis is not None:
            await cls.redis.wait_closed()
        if cls._instance is not None:
            cls._instance = None