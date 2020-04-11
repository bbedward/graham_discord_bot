from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from models.constants import Constants
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages
from util.env import Env
from util.regex import RegexUtil, AmountMissingException
from util.number import NumberUtil
from util.validators import Validators
from db.models.stats import Stats
from db.models.transaction import Transaction
from db.models.user import User
from db.redis import RedisDB
from tasks.transaction_queue import TransactionQueue

import asyncio
import config
import cogs.rain as rain
import secrets
from util.util import Utils

## Command documentation
TIP_INFO = CommandInfo(
    triggers = ["ban", "b"] if Env.banano() else ["ntip", "n"],
    overview = "Send a tip to mentioned users",
    details = f"Tip specified amount to mentioned user(s) (**minimum tip is {Constants.TIP_MINIMUM} {Constants.TIP_UNIT}**)" +
        "\nThe recipient(s) will be notified of your tip via private message" +
        "\nSuccessful tips will be deducted from your available balance immediately.\n" +
     f"Example: `{config.Config.instance().command_prefix}{'ban' if Env.banano() else 'ntip'} 2 @user1 @user2` would send 2 to user1 and 2 to user2"
)
TIPSPLIT_INFO = CommandInfo(
    triggers = ["bansplit", "bs"] if Env.banano() else ["ntipsplit", "ns"],
    overview = "Split a tip among mentioned users",
    details = f"Divide the specified amount between mentioned user(s) (**minimum tip is {Constants.TIP_MINIMUM} {Constants.TIP_UNIT}**)" +
        "\nThe recipient(s) will be notified of your tip via private message" +
        "\nSuccessful tips will be deducted from your available balance immediately.\n" +
     f"Example: `{config.Config.instance().command_prefix}{'bansplit' if Env.banano() else 'ntipsplit'} 2 @user1 @user2` would send 1 to user1 and 2 to user2"
)
TIPRANDOM_INFO = CommandInfo(
    triggers = ["banrandom", "br"] if Env.banano() else ["ntiprandom", "ntr"],
    overview = "Tip an active user at random.",
    details = f"Tips the specified amount to an active user at random (**minimum tip is {Constants.TIPRANDOM_MINIMUM} {Constants.TIP_UNIT}**)" +
        "\nThe recipient will be notified of your tip via private message and you'll be notified of who the random recipient was."
)
TIPAUTHOR_INFO = CommandInfo(
    triggers = ["banauthor", "tipauthor"] if Env.banano() else ["tipauthor"],
    overview = "Donate to support my creator",
    details = f"Support the author of this bot (bbedward)"
)

class TipsCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx: Context):
        ctx.error = False
        # Remove duplicate mentions
        ctx.message.mentions = set(ctx.message.mentions)
        # Only allow tip commands in public channels
        msg = ctx.message
        if ChannelUtil.is_private(msg.channel):
            ctx.error = True
            return
        else:
            # Check admins
            ctx.god = msg.author.id in config.Config.instance().get_admin_ids()
            ctx.admin = False
            author: discord.Member = msg.author
            for role in author.roles:
                if role.id in config.Config.instance().get_admin_roles():
                    ctx.admin = True
                    break
        # Check paused
        if await RedisDB.instance().is_paused():
            ctx.error = True
            await Messages.send_error_dm(msg.author, f"Transaction activity is currently suspended. I'll be back online soon!")
            return
        # See if user exists in DB
        user = await User.get_user(msg.author)
        if user is None:
            ctx.error = True
            await Messages.send_error_dm(msg.author, f"You should create an account with me first, send me `{config.Config.instance().command_prefix}help` to get started.")
            return
        elif user.frozen:
            ctx.error = True
            await Messages.send_error_dm(msg.author, f"Your account is frozen. Contact an admin if you need further assistance.")
            return
        # Update name, if applicable
        await user.update_name(msg.author.name)
        ctx.user = user
        # See if amount meets tip_minimum requirement
        try:
            send_amount = RegexUtil.find_float(msg.content)
            if ctx.command.name == 'tiprandom_cmd' and send_amount < Constants.TIPRANDOM_MINIMUM:
                raise AmountMissingException(f"Tip random amount is too low, minimum is {Constants.TIPRANDOM_MINIMUM}")
            elif ctx.command.name != 'tiprandom_cmd' and send_amount < Constants.TIP_MINIMUM:
                raise AmountMissingException(f"Tip amount is too low, minimum is {Constants.TIP_MINIMUM}")
            elif Validators.too_many_decimals(send_amount):
                await Messages.send_error_dm(ctx.message.author, f"You are only allowed to use {Env.precision_digits()} digits after the decimal.")
                ctx.error = True
                return
        except AmountMissingException:
            ctx.error = True
            if ctx.command.name == 'tip_cmd':
                await Messages.send_usage_dm(msg.author, TIP_INFO)
            elif ctx.command.name == 'tipsplit_cmd':
                await Messages.send_usage_dm(msg.author, TIPSPLIT_INFO)
            elif ctx.command.name == 'tiprandom_cmd':
                await Messages.send_usage_dm(msg.author, TIPRANDOM_INFO)
            return
        ctx.send_amount = send_amount

    @commands.command(aliases=TIP_INFO.triggers)
    async def tip_cmd(self, ctx: Context):
        if ctx.error:
            await Messages.add_x_reaction(ctx.message)
            return

        msg = ctx.message
        user = ctx.user
        send_amount = ctx.send_amount

        # Get all eligible users to tip in their message
        users_to_tip = []
        for m in msg.mentions:
            if not m.bot and m.id != msg.author.id:
                users_to_tip.append(m)
        if len(users_to_tip) < 1:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"No users you mentioned are eligible to receive tips.")
            return

        # See how much they need to make this tip.
        amount_needed = send_amount * len(users_to_tip)
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount_needed > available_balance:
            await Messages.add_x_reaction(ctx.message)
            await Messages.send_error_dm(msg.author, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount_needed} {Env.currency_symbol()}**")
            return

        # Make the transactions in the database
        tx_list = []
        task_list = []
        for u in users_to_tip:
            tx = await Transaction.create_transaction_internal(
                sending_user=user,
                amount=send_amount,
                receiving_user=u
            )
            if tx is not None:
                tx_list.append(tx)
                if not await user.is_muted_by(u.id):
                    task_list.append(
                        Messages.send_basic_dm(
                            member=u,
                            message=f"You were tipped **{send_amount} {Env.currency_symbol()}** by {msg.author.name.replace('`', '')}.\nUse `{config.Config.instance().command_prefix}mute {msg.author.id}` to disable notifications for this user.",
                            skip_dnd=True
                        )
                    )
        if len(tx_list) < 1:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"No users you mentioned are eligible to receive tips.")
            return
        # Send DMs in background, this is an attempt to avoid discord throttling us for sending too many at once
        asyncio.ensure_future(Utils.run_task_list(task_list))
        # Add reactions
        await Messages.add_tip_reaction(msg, send_amount * len(tx_list))
        # Queue the actual sends
        for tx in tx_list:
            await TransactionQueue.instance().put(tx)
        # Update stats
        stats: Stats = await user.get_stats(server_id=msg.guild.id)
        if msg.channel.id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(send_amount * len(tx_list))

    @commands.command(aliases=TIPSPLIT_INFO.triggers)
    async def tipsplit_cmd(self, ctx: Context):
        if ctx.error:
            await Messages.add_x_reaction(ctx.message)
            return

        msg = ctx.message
        user = ctx.user
        send_amount = ctx.send_amount

        # Get all eligible users to tip in their message
        users_to_tip = []
        for m in msg.mentions:
            if not m.bot and m.id != msg.author.id:
                users_to_tip.append(m)
        if len(users_to_tip) < 1:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"No users you mentioned are eligible to receive tips.")
            return

        individual_send_amount = NumberUtil.truncate_digits(send_amount / len(users_to_tip), max_digits=Env.precision_digits())
        if individual_send_amount < Constants.TIP_MINIMUM:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"Tip amount too small, each user needs to receive at least {Constants.TIP_MINIMUM}. With your tip they'd only be getting {individual_send_amount}")
            return

        # See how much they need to make this tip.
        amount_needed = individual_send_amount * len(users_to_tip)
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount_needed > available_balance:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount_needed} {Env.currency_symbol()}**")
            return

        # Make the transactions in the database
        tx_list = []
        task_list = []
        for u in users_to_tip:
            tx = await Transaction.create_transaction_internal(
                sending_user=user,
                amount=individual_send_amount,
                receiving_user=u
            )
            if tx is not None:
                tx_list.append(tx)
                if not await user.is_muted_by(u.id):
                    task_list.append(
                        Messages.send_basic_dm(
                            member=u,
                            message=f"You were tipped **{individual_send_amount} {Env.currency_symbol()}** by {msg.author.name.replace('`', '')}.\nUse `{config.Config.instance().command_prefix}mute {msg.author.id}` to disable notifications for this user.",
                            skip_dnd=True
                        )
                    )
        if len(tx_list) < 1:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"No users you mentioned are eligible to receive tips.")
            return
        # Send DMs
        asyncio.ensure_future(Utils.run_task_list(task_list))
        # Add reactions
        await Messages.add_tip_reaction(msg, amount_needed)
        # Queue the actual sends
        for tx in tx_list:
            await TransactionQueue.instance().put(tx)
        # Update stats
        stats: Stats = await user.get_stats(server_id=msg.guild.id)
        if msg.channel.id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(amount_needed)

    @commands.command(aliases=TIPRANDOM_INFO.triggers)
    async def tiprandom_cmd(self, ctx: Context):
        if ctx.error:
            await Messages.add_x_reaction(ctx.message)
            return

        msg = ctx.message
        user = ctx.user
        send_amount = ctx.send_amount

        # Check anti-spam
        if not ctx.god and await RedisDB.instance().exists(f"tiprandomspam{msg.guild.id}{msg.author.id}"):
            await Messages.add_timer_reaction(msg)
            await Messages.send_basic_dm(msg.author, "You can only tiprandom once every minute")
            return

        active_users = await rain.RainCog.get_active(ctx, excluding=msg.author.id)

        if len(active_users) < Constants.RAIN_MIN_ACTIVE_COUNT:
            await Messages.send_error_dm(msg.author, f"There aren't enough active people to do a random tip. Only **{len(active_users)}** are active, but I'd like to see at least **{Constants.RAIN_MIN_ACTIVE_COUNT}**")
            return

        target_user = secrets.choice(active_users)

        # See how much they need to make this tip.
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if send_amount > available_balance:
            await Messages.add_x_reaction(ctx.message)
            await Messages.send_error_dm(msg.author, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{send_amount} {Env.currency_symbol()}**")
            return

        # Make the transactions in the database
        tx = await Transaction.create_transaction_internal_dbuser(
            sending_user=user,
            amount=send_amount,
            receiving_user=target_user
        )
        task_list = []
        if not await user.is_muted_by(target_user.id):
            task_list.append(
                Messages.send_basic_dm(
                    member=msg.guild.get_member(target_user.id),
                    message=f"You were randomly selected and received **{send_amount} {Env.currency_symbol()}** from {msg.author.name.replace('`', '')}.\nUse `{config.Config.instance().command_prefix}mute {msg.author.id}` to disable notifications for this user.",
                    skip_dnd=True
                )
            )
        task_list.append(
            Messages.send_basic_dm(
                member=msg.author,
                message=f'"{target_user.name}" was the recipient of your random tip of {send_amount} {Env.currency_symbol()}'
            )
        )
        asyncio.ensure_future(Utils.run_task_list(task_list))
        # Add reactions
        await Messages.add_tip_reaction(msg, send_amount)
        # Queue the actual send
        await TransactionQueue.instance().put(tx)
        # anti spam
        await RedisDB.instance().set(f"tiprandomspam{msg.guild.id}{msg.author.id}", "as", expires=60)
        # Update stats
        stats: Stats = await user.get_stats(server_id=msg.guild.id)
        if msg.channel.id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(send_amount)

    @commands.command(aliases=TIPAUTHOR_INFO.triggers)
    async def tipauthor_cmd(self, ctx: Context):
        if ctx.error:
            await Messages.add_x_reaction(ctx.message)
            return

        msg = ctx.message
        user = ctx.user
        send_amount = ctx.send_amount

        # See how much they need to make this tip.
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if send_amount > available_balance:
            await Messages.add_x_reaction(ctx.message)
            await Messages.send_error_dm(msg.author, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{send_amount} {Env.currency_symbol()}**")
            return

        # Make the transactions in the database
        tx_list = []
        task_list = []
        tx = await Transaction.create_transaction_external(
            sending_user=user,
            amount=send_amount,
            destination=Env.donation_address()
        )
        # Add reactions
        await msg.add_reaction('\U00002611')
        await msg.add_reaction('\U0001F618')
        await msg.add_reaction('\u2764')
        await msg.add_reaction('\U0001F499')
        await msg.add_reaction('\U0001F49B')
        # Queue the actual send
        await TransactionQueue.instance().put(tx)
        # Update stats
        stats: Stats = await user.get_stats(server_id=msg.guild.id)
        if msg.channel.id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(send_amount)