import datetime

import discord
from tortoise import fields
from tortoise.models import Model
from tortoise.transactions import in_transaction

import db.models.account as acct
import db.models.stats as stats
from models.constants import Constants
from rpc.client import RPCClient
from util.env import Env

class User(Model):
    id = fields.BigIntField(pk=True, generated=False)
    name = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"

    @classmethod
    async def create_or_fetch_user(cls, user: discord.User) -> 'User':
        """Create a user if they don't exist, raises OperationalError if database error occurs"""
        dbuser: 'User' = await cls.filter(id=user.id).prefetch_related('account').first()
        if dbuser is None:
            async with in_transaction() as conn:
                # Create user and return them
                dbuser = User(
                    id = user.id,
                    name = user.name
                )
                await dbuser.save(using_db=conn)
                # Create an account
                address = await RPCClient.instance().account_create()
                if address is None:
                    raise Exception("RPC account create failed")
                account = acct.Account(
                    user = dbuser,
                    address = address
                )
                await account.save(using_db=conn)
                dbuser.account = account
        return dbuser

    @classmethod
    async def get_user(cls, user: discord.User) -> 'User':
        """Get discord user from database, return None if they haven't registered"""
        return await cls.filter(id=user.id).prefetch_related('account').first()

    async def update_name(self, name: str):
        """Update discord user name in database"""
        if name != self.name:
            self.name = name
            await self.save(update_fields=['name'])

    async def get_address(self) -> str:
        """Get account address of user"""
        if isinstance(self.account, acct.Account):
            return self.account.address
        account = await self.account.first()
        if account is not None:
            return account.address
        # Create an account
        address = await RPCClient.instance().account_create()
        if address is None:
            raise Exception("RPC account create failed")
        account = acct.Account(
            user = self,
            address = address
        )
        async with in_transaction() as conn:
            await account.save(using_db=conn)
        return address

    async def get_stats(self, server_id: int) -> stats.Stats:
        """Return Stats object for this user for the given server"""
        user_stats = await self.stats.filter(server_id=server_id).first()
        if user_stats is None:
            user_stats = stats.Stats(
                user=self,
                server_id=server_id
            )
            async with in_transaction() as conn:
                await user_stats.save(using_db=conn)
        return user_stats

    async def get_pending(self) -> int:
        """Get pending amounts in internal database as a sum (in RAW)
            returns a tuple (pending_send, pending_receive)"""
        sent_transactions = await self.sent_transactions.filter(block_hash=None).all()
        received_transactions = await self.received_transactions.filter(block_hash=None).all()
        pending_send = 0
        pending_receive = 0
        for stx in sent_transactions:
            pending_send += int(stx.amount)
        for ptx in received_transactions:
            pending_receive += int(ptx.amount)
        return (pending_send, pending_receive)

    async def get_available_balance(self) -> int:
        """Get available balance of user (in RAW)"""
        address = await self.get_address()
        pending_send, pending_receive = await self.get_pending()
        actual = await RPCClient.instance().account_balance(address)
        return int(actual['balance']) - pending_send

    async def get_available_balance_dec(self) -> float:
        """Get available balance of user (in normal unit)"""
        address = await self.get_address()
        pending_send, pending_receive = await self.get_pending()
        actual = await RPCClient.instance().account_balance(address)
        available = int(actual['balance']) - pending_send
        return Env.raw_to_amount(available)

    async def get_next_withdraw_s(self) -> int:
        """Get how long ago in seconds the user must wait until they can withdraw again"""
        # select * from transactions where user_id = ? order by created_at desc limit 1
        last_withdraw = await self.sent_transactions.filter(receiving_user=None).order_by('-created_at').first()
        if last_withdraw is None:
            return -1
        # Get how many seconds until they can withdraw again
        delta = (datetime.datetime.utcnow() - last_withdraw.created_at).total_seconds()
        return int(Constants.WITHDRAW_COOLDOWN - delta)