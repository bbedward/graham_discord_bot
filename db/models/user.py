from tortoise.models import Model
from tortoise.transactions import in_transaction
from tortoise import fields
from rpc.client import RPCClient

import discord
import db.models.account as acct
import db.models.stats as stats

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
        dbuser: 'User' = await cls.filter(id=user.id).first()
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
            return dbuser
        return await cls.filter(id=user.id).first()

    @classmethod
    async def get_user(cls, user: discord.User) -> 'User':
        """Get discord user from database, return None if they haven't registered"""
        return await cls.filter(id=user.id).first()


    async def get_address(self) -> str:
        """Get account address of user"""
        account = await self.account.all()
        if len(account) > 0:
            return account[0].address
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
                server_id=server_id
            )
            async with in_transaction() as conn:
                await user_stats.save(using_db=conn)
        return user_stats

    async def get_pending(self) -> int:
        """Get pending amounts in internal database as a sum (in RAW)
            returns a tuple (pending_send, pending_receive)"""
        sent_transactions = self.sent_transactions.filter(block_hash=None)
        received_transactions = self.received_transactions.filter(block_hash=None)
        pending_send = 0
        pending_receive = 0
        for stx in sent_transactions:
            pending_send += int(stx.amount)
        for ptx in received_transactions:
            pending_receive += int(ptx.amount) * -1
        return (pending_send, pending_receive)

    async def get_available_balance(self) -> int:
        """Get available balance of user (in RAW)"""
        address = await self.get_address()
        pending_send, pending_receive = await self.get_pending()
        actual = await RPCClient.instance().account_balance(address)
        return int(actual['balance']) - pending_send