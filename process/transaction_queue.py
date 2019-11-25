import aioprocessing
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
            cls.queue = aioprocessing.AioQueue()
            cls.logger = logging.getLogger()
        return cls._instance

    async def put(self, tx: Transaction):
        queue: aioprocessing.AioQueue = self.queue
        await queue.coro_put(tx)

    async def process_queue(self) -> Transaction:
        queue: aioprocessing.AioQueue = self.queue
        while True:
            try:
                tx: Transaction = await queue.coro_get()
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