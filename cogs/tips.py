from discord.ext import commands
from discord.ext.commands import Bot, Context
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
import config

## Command documentation
TIP_INFO = CommandInfo(
    triggers = ["ban", "b"] if Env.banano() else ["ntip", "n"],
    overview = "Send a tip to mentioned users",
    details = f"Tip specified amount to mentioned user(s) (minimum tip is {Constants.TIP_MINIMUM} {Constants.TIP_UNIT})" +
        "\nThe recipient(s) will be notified of your tip via private message" +
        "\nSuccessful tips will be deducted from your available balance immediately.\n" +
     f"{config.Config.instance().command_prefix}{'ban' if Env.banano() else 'ntip'} 2 @user1 @user2` would send 2 to user1 and 2 to user2"
)

class Tips(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx: Context):
        # TODO - incorporate frozen, paused,
        # Only allow tip commands in public channels
        msg = ctx.message
        if ChannelUtil.is_private(msg.channel):
            raise Exception(f"invoked command {ctx.command.name} in private channel")
        # See if user exists in DB
        user = await User.get_user(msg.author)
        if user is None:
            ctx.error = True
            await Messages.send_error_dm(msg.author, f"You should create an account with me first, send me `{config.Config.instance().command_prefix}help` to get started.")
            raise Exception(f"invoked command {ctx.command.name} without creating account")
        ctx.user = user
        # See if amount meets tip_minimum requirement
        try:
            send_amount = RegexUtil.find_float(msg.content)
            if send_amount < Constants.TIP_MINIMUM:
                raise AmountMissingException(f"Tip amount is too low, minimum is {Constants.TIP_MINIMUM}")
        except AmountMissingException:
            ctx.error = True
            await Messages.send_usage_dm(msg.author, TIP_INFO)
            raise Exception(f"invoked command {ctx.command.name} but didn't include amount")
        ctx.send_amount = send_amount
        # Remove duplicate mentions
        ctx.message.mentions = set(ctx.message.mentions)

    @commands.command(aliases=TIP_INFO.triggers)
    async def tip_cmd(self, ctx: Context):
        msg = ctx.message
        user = ctx.user
        send_amount = ctx.send_amount

        # Get all eligible users to tip in their message
        users_to_tip = []
        for m in msg.mentions:
            # TODO - consider tip banned
            if not m.bot and m.id != msg.author.id:
                users_to_tip.append(m)
        if len(users_to_tip) < 1:
            await Messages.send_error_dm(msg.author, f"No users you mentioned are eligible to receive tips.")
            return

        # See how much they need to make this tip.
        amount_needed = send_amount * len(users_to_tip)
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount_needed > available_balance:
            await Messages.send_error_dm(msg.author, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount_needed} {Env.currency_symbol()}**")
            return

        # Make the transactions in the database
        tx_list = []
        for u in users_to_tip:
            tx = await Transaction.create_transaction_internal(
                sending_user=user,
                amount=send_amount,
                receiving_user=u
            )
            tx_list.append(tx)
        # TODO - tip notification
        # Add reactions
        await Messages.add_tip_reaction(msg, send_amount * len(tx_list))
        # Queue the actual sends
        for tx in tx_list:
            await TransactionQueue.instance().put(tx)
        # Update stats
        stats: Stats = await user.get_stats(server_id=msg.guild.id)
        await stats.update_tip_stats(send_amount * len(tx_list))
        