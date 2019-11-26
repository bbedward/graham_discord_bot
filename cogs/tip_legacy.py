from discord.ext import commands
from discord.ext.commands import Bot, Context
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages
from db.models.user import User
import config
"""
from models.command import CommandInfo
from models.constants import Constants
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages
from util.env import Env
from util.regex import RegexUtil, AmountMissingException
from db.models.stats import Stats
from db.models.transaction import Transaction
from db.models.user import User
from tasks.transaction_queue import TransactionQueue

import asyncio
import config"""

class TipLegacy(commands.Cog):
    """Just show information about the new tip command for NANO bot"""
    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx: Context):
        msg = ctx.message
        if ChannelUtil.is_private(msg.channel):
            raise Exception(f"invoked command {ctx.command.name} in private channel")
        # See if user exists in DB
        user = await User.get_user(msg.author)
        if user is None:
            ctx.error = True
            await Messages.send_error_dm(msg.author, f"You should create an account with me first, send me `{config.Config.instance().command_prefix}help` to get started.")
            raise Exception(f"invoked command {ctx.command.name} without creating account")

    @commands.command(aliases=['t'])
    async def tip(self, ctx: Context):
        msg = ctx.message

        await Messages.send_error_dm(
            member=msg.author,
            message=f"**WARNING** Tip units are in NANO now! That means tip amounts are **1000000x** larger than they used to be. You need to use `{config.Config.instance().command_prefix}ntip` to send nano tips.\nExample: `{config.Config.instance().command_prefix}ntip 0.00001 @bbedward` - sends 0.00001 NANO to bbedward"
        )