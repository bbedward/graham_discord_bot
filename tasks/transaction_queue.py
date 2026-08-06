import asyncio
import logging

from discord.ext.commands import Bot
from tortoise.transactions import in_transaction
from db.models.transaction import Transaction
from util.env import Env

MAX_RETRIES = 20

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
            cls.inflight = set()
        return cls._instance

    async def put(self, tx: Transaction):
        # The periodic re-queue reads block_hash=None straight from the DB, so a send that is
        # still in flight would be queued a second time without this
        if str(tx.id) in self.inflight:
            self.logger.debug(f"Skipping queue of {tx.id}, already in flight")
            return
        self.inflight.add(str(tx.id))
        await self.queue.put(tx)

    async def notify_user(self, tx: Transaction, hash: str):
        if tx.destination == Env.donation_address():
            return
        bot: Bot = self.bot
        user = bot.get_user(tx.sending_user.id)
        if user is None:
            self.logger.warn(f"User with ID {tx.sending_user.id} was not found, so I couldn't notify them of their withdrawal")
            return
        if Env.banano():
            await user.send(f"Withdraw processed: https://creeper.banano.cc/explorer/block/{hash}")
        else:
            await user.send(f"Withdraw processed: https://blocklattice.io/block/{hash}")

    async def retry(self, tx: Transaction):
        delay = (tx.retries + 1) * 5
        tx.retries += 1
        try:
            async with in_transaction() as conn:
                await tx.save(update_fields=['retries'], using_db=conn)
            await asyncio.sleep(delay)
            await self.queue.put(tx)
        except Exception:
            self.logger.exception(f"Failed to re-queue transaction {tx.id}")
            self.inflight.discard(str(tx.id))

    async def mark_failed(self, tx: Transaction):
        self.logger.error(f"Giving up on transaction {tx.id} after {tx.retries} retries")
        tx.failed = True
        async with in_transaction() as conn:
            await tx.save(update_fields=['failed'], using_db=conn)

    async def retry_or_fail(self, tx: Transaction) -> bool:
        if tx.retries >= MAX_RETRIES:
            await self.mark_failed(tx)
            return False
        asyncio.ensure_future(self.retry(tx))
        return True

    async def queue_consumer(self):
        while True:
            tx = None
            retrying = False
            try:
                tx = await self.queue.get()
                res = await tx.send()
                if res is None:
                    retrying = await self.retry_or_fail(tx)
                elif tx.receiving_user is None:
                    asyncio.ensure_future(self.notify_user(tx=tx, hash=res))
            except KeyboardInterrupt:
                break
            except Exception:
                self.logger.exception(f"Error occured when processing transaction {tx.id if tx is not None else 'unknown'}")
                if tx is not None:
                    try:
                        retrying = await self.retry_or_fail(tx)
                    except Exception:
                        self.logger.exception("Failed to schedule retry")
            finally:
                if tx is not None and not retrying:
                    self.inflight.discard(str(tx.id))
