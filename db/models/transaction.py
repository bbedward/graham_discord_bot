import discord
from tortoise import fields
from tortoise.models import Model
from tortoise.transactions import in_transaction

import db.models.giveaway as gway
import db.models.user as usr

from rpc.client import RPCClient
from util.env import Env


class Transaction(Model):
    id = fields.UUIDField(pk=True)
    sending_user = fields.ForeignKeyField('db.User', related_name='sent_transactions', index=True)
    receiving_user = fields.ForeignKeyField('db.User', related_name='received_transactions', null=True, index=True)
    destination = fields.CharField(max_length=65, null=True)
    block_hash = fields.CharField(max_length=64, index=True, null=True)
    amount = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    modified_at = fields.DatetimeField(auto_now=True)
    giveaway = fields.ForeignKeyField('db.Giveaway', related_name='giveaway_transactions', null=True, index=True)
    # These used to be a bare class attribute (retries = 0), which meant the retry count was never
    # persisted. Every re-queue produced a fresh object with retries back at 0, so the "give up after
    # 20 tries" cap in the queue consumer never actually stopped anything - a transaction that could
    # not be recorded was re-sent every 10 minutes forever.
    retries = fields.IntField(default=0)
    failed = fields.BooleanField(default=False)

    class Meta:
        table = 'transactions'

    @staticmethod
    async def create_transaction_internal(
                                sending_user: usr.User,
                                amount: float,
                                receiving_user: discord.User) -> 'Transaction':
        """Create a transaction in the database, among discord users"""
        # See if receiving user exists in our database
        receiving_user_db : usr.User = await usr.User.create_or_fetch_user(receiving_user)
        if receiving_user_db.tip_banned:
            return None
        # Create transaction
        tx = None
        async with in_transaction() as conn:
            tx = Transaction(
                sending_user = sending_user,
                amount = str(Env.amount_to_raw(amount)),
                destination = await receiving_user_db.get_address(),
                receiving_user = receiving_user_db
            )
            await tx.save(using_db=conn)
        return tx

    @staticmethod
    async def create_transaction_internal_dbuser(
                                sending_user: usr.User,
                                amount: float,
                                receiving_user: usr.User) -> 'Transaction':
        """Create a transaction in the database, among discord users"""
        # Create transaction
        tx = None
        async with in_transaction() as conn:
            tx = Transaction(
                sending_user = sending_user,
                amount = str(Env.amount_to_raw(amount)),
                destination = await receiving_user.get_address(),
                receiving_user = receiving_user
            )
            await tx.save(using_db=conn)
        return tx

    @staticmethod
    async def create_transaction_external(
                                sending_user: usr.User,
                                amount: float,
                                destination: str,
                                raw_amt: str = None) -> 'Transaction':
        # Create transaction
        tx = None
        async with in_transaction() as conn:
            tx = Transaction(
                sending_user = sending_user,
                amount = raw_amt if raw_amt else str(Env.amount_to_raw(amount)),
                destination = destination,
                receiving_user = None
            )
            await tx.save(using_db=conn)
        return tx

    @staticmethod
    async def create_transaction_giveaway(
                                sending_user: usr.User,
                                amount: float,
                                giveaway: gway.Giveaway,
                                conn = None) -> 'Transaction':
        """Create a transaction in the database, among discord users"""
        # Create transaction
        tx = None
        tx = Transaction(
            sending_user = sending_user,
            amount = str(Env.amount_to_raw(amount)),
            giveaway=giveaway
        )
        await tx.save(using_db=conn)
        return tx

    async def send(self) -> str:
        if self.block_hash is not None:
            return self.block_hash
        elif self.destination is None:
            return
        source = await self.sending_user.get_address()
        # Anything past the first attempt has to be reconciled against the chain before we send
        # again. A previous attempt can have landed on-chain even though the node handed us back no
        # block, and we cannot assume the node's send `id` de-dupe caught it. Adopt the existing
        # block instead of publishing a second one.
        if self.retries > 0:
            existing = await RPCClient.instance().find_existing_send(
                source=source,
                destination=self.destination,
                amount=self.amount
            )
            if existing is not None:
                async with in_transaction() as conn:
                    self.block_hash = existing
                    await self.save(using_db=conn)
                return existing
        # Make transaction internal
        resp = await RPCClient.instance().send(
            id=str(self.id),
            source=source,
            destination=self.destination,
            amount=self.amount
        )
        if resp is not None:
            async with in_transaction() as conn:
                self.block_hash = resp
                await self.save(using_db=conn)
        return resp
