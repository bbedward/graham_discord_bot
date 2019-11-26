import asyncio
import logging

from discord.ext.commands import Bot
from db.models.transaction import Transaction
from util.env import Env

class TransactionQueue(object):
    _instance = None

    def __init__(self):
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls, bot: Bot = None) -> 'TransactionQueue':
        if cls._instance is None and bot is None:
            raise ValueError("bot cannot be None on first call")
        elif cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls.queue = asyncio.Queue(maxsize=0)
            cls.logger = logging.getLogger()
            cls.bot = bot
        return cls._instance

    async def put(self, tx: Transaction):
        queue: asyncio.Queue = self.queue
        await queue.put(tx)

    async def notify_user(self, tx: Transaction, hash: str):
        bot: Bot = self.bot
        user = bot.get_user(tx.sending_user.id)
        if user is None:
            self.logger.warn(f"User with ID {tx.sending_user.id} was not found, so I couldn't notify them of their withdraw")
            return
        if Env.banano():
            await user.send(f"Withdraw processed: https://creeper.banano.cc/explorer/block/{hash}")
        else:
            await user.send(f"Withdraw processed: https://nanocrawler.cc/explorer/block/{hash}")

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
                elif tx.receiving_user is None:
                    # Notify user their withdraw was processed
                    asyncio.ensure_future(self.notify_user(tx=tx, hash=res))
            except KeyboardInterrupt:
                break
            except Exception:
                self.logger.exception("Error occured when processing transaction queue")