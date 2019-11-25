import asyncio
import logging

from db.models.transaction import Transaction

class TransactionQueue(object):
    _instance = None

    def __init__(self):
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls) -> 'TransactionQueue':
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls.queue = asyncio.Queue(maxsize=0)
            cls.logger = logging.getLogger()
        return cls._instance

    async def put(self, tx: Transaction):
        queue: asyncio.Queue = self.queue
        await queue.put(tx)

    async def queue_consumer(self):
        queue: asyncio.Queue = self.queue
        while True:
            try:
                tx: Transaction = await queue.get()
                res = await tx.send()
                if res is None:
                    tx.retries += 1
                    if tx.retries < 3:
                        # Retry this transaction by placing it on the end of the queue
                        await self.put(tx)
            except KeyboardInterrupt:
                break
            except Exception:
                self.logger.exception("Error occured when processing transaction queue")