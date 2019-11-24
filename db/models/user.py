from tortoise.models import Model
from tortoise.transactions import in_transaction
from tortoise import fields
from rpc.client import RPCClient

import discord
import db.models.account as acct

class User(Model):
    id = fields.BigIntField(pk=True, generated=False)
    name = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"

    @classmethod
    async def create_or_fetch_user(cls, user : discord.User) -> 'User':
        """Create a user if they don't exist, raises OperationalError if database error occurs"""
        dbuser: 'User' = await cls.filter(id=user.id).first()
        if dbuser is None:
            async with in_transaction() as connection:
                # Create user and return them
                dbuser = User(
                    id = user.id,
                    name = user.name
                )
                await dbuser.save(using_db=connection)
                # Create an account
                address = await RPCClient.instance().account_create()
                if address is None:
                    raise Exception("RPC account create failed")
                account = acct.Account(
                    user = dbuser,
                    address = address
                )
                await account.save(using_db=connection)
            return dbuser
        return await cls.filter(id=user.id).first()

    async def get_address(self) -> acct.Account:
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
        async with in_transaction() as connection:
            await account.save(using_db=connection)
        return address