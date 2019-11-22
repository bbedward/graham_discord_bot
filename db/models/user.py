from tortoise.models import Model
from tortoise.transactions import in_transaction
from tortoise import fields
from config import Config
from db.models.account import Account

import discord

class User(Model):
    id = fields.BigIntField(pk=True)
    name = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"

    @classmethod
    async def create_or_fetch_user(cls, user : discord.User) -> User:
        """Create a user if they don't exist, raises OperationalError if database error occurs"""
        user: Account = await cls.filter(id=user.id).first()
        if user is None:
            async with in_transaction() as connection:
                # Create user and return them
                user = User(
                    id = user.id,
                    name = user.name
                )
                await user.save(using_db=connection)
                # Create an account
                account = await Config.rpc.account_create()
                if account is None:
                    raise Exception("RPC account create failed")
                account = Account(
                    user = user,
                    account = account
                )
                await account.save(using_db=connection)
            return user
        return await cls.filter(id=user.id).first()