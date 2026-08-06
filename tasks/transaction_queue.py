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
            # IDs of transactions that are queued or currently being sent
            cls.inflight = set()
        return cls._instance

    def clear(self):
        for _ in range(self.queue.qsize()):
            try:
                tx = self.queue.get_nowait()
                self.inflight.discard(str(tx.id))
                self.queue.task_done()
            except asyncio.QueueEmpty:
                pass
            except ValueError:
                pass

    async def put(self, tx: Transaction):
        queue: asyncio.Queue = self.queue
        # Never allow two objects representing the same DB row to be in flight at once. The periodic
        # re-queue reads block_hash=None straight from the DB, so a send that is currently in flight
        # (the RPC call has a 300s timeout) still looks unprocessed and would be queued a second time.
        # The only thing stopping that from becoming a real double spend today is node side dedup on
        # the send id, which is not something this bot should be betting user funds on.
        if str(tx.id) in self.inflight:
            self.logger.debug(f"Skipping queue of {tx.id}, already in flight")
            return
        self.inflight.add(str(tx.id))
        await queue.put(tx)

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
        """Re-queue a transaction after a delay. The tx stays in `inflight` for the whole delay so
        the periodic re-queue can't slip a second copy of the same row in behind it."""
        # Was `tx.retries + 1 * 5`, which is `tx.retries + 5` - the backoff never actually backed off
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
        """Stop retrying this transaction. It stays in the DB for an admin to look at, but the
        periodic re-queue will leave it alone instead of re-sending it every 10 minutes forever."""
        self.logger.error(f"Giving up on transaction {tx.id} after {tx.retries} retries")
        tx.failed = True
        async with in_transaction() as conn:
            await tx.save(update_fields=['failed'], using_db=conn)

    async def queue_consumer(self):
        queue: asyncio.Queue = self.queue
        while True:
            tx = None
            retrying = False
            try:
                tx = await queue.get()
                res = await tx.send()
                if res is None:
                    if tx.retries < MAX_RETRIES:
                        # Retry this transaction by placing it on the end of the queue
                        retrying = True
                        asyncio.ensure_future(self.retry(tx))
                    else:
                        await self.mark_failed(tx)
                elif tx.receiving_user is None:
                    # Notify user their withdraw was processed
                    asyncio.ensure_future(self.notify_user(tx=tx, hash=res))
            except KeyboardInterrupt:
                break
            except Exception:
                # A send that raises here is the dangerous case: the node may have created and
                # broadcast the block before the connection died, so the funds are gone but
                # block_hash is still NULL in our DB. Log loudly and let the re-queue pick it up,
                # but count it as a retry so it cannot loop forever.
                self.logger.exception(f"Error occured when processing transaction {tx.id if tx is not None else 'unknown'}")
                if tx is not None:
                    try:
                        if tx.retries < MAX_RETRIES:
                            retrying = True
                            asyncio.ensure_future(self.retry(tx))
                        else:
                            await self.mark_failed(tx)
                    except Exception:
                        self.logger.exception("Failed to schedule retry")
            finally:
                if tx is not None and not retrying:
                    self.inflight.discard(str(tx.id))
