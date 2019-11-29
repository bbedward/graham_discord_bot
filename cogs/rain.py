
import discord
from discord.ext import commands
from discord.ext.commands import Bot, Context

from models.command import CommandInfo
from util.env import Env

import asyncio
import config
import datetime
import json
import logging
from util.regex import AmountAmbiguousException, AmountMissingException, RegexUtil
from util.validators import Validators
from util.util import Utils
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages
from db.models.user import User
from db.redis import RedisDB
from typing import List
from models.constants import Constants
from util.number import NumberUtil
from db.models.transaction import Transaction
from tasks.transaction_queue import TransactionQueue

# Commands Documentation
RAIN_INFO = CommandInfo(
    triggers = ["brain" if Env.banano() else "nrain"],
    overview = "Distribute a tip amount amongst active users",
    details = "Distribute amount amongst active users." +
                f"\nExample: `{config.Config.instance().command_prefix}{'b' if Env.banano() else 'n'}rain 1000` will distribute 1000 {Env.currency_symbol()} between everyone who is active." +
                f"\n **minimum amount to rain: {config.Config.instance().get_rain_minimum()} {Env.currency_symbol()}**"
)

class Rain(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.logger = logging.getLogger()

    async def cog_before_invoke(self, ctx: Context):
        ctx.error = False
        msg = ctx.message
        # TODO - check frozen
        if ChannelUtil.is_private(ctx.message.channel):
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
            await Messages.send_error_dm(msg.author, f"Transaction activity is currently suspended. I'll be back online soon!")
            return

        # Check anti-spam
        if not ctx.god and await RedisDB.instance().exists(f"rainspam{msg.author.id}"):
            await Messages.add_timer_reaction(msg)
            await Messages.send_basic_dm(msg.author, "You can only rain once every 5 minutes")
            return

        # Parse some info
        try:
            ctx.send_amount = RegexUtil.find_send_amounts(msg.content)
            if Validators.too_many_decimals(ctx.send_amount):
                await Messages.send_error_dm(msg.author, f"You are only allowed to use {Env.precision_digits()} digits after the decimal.")
                ctx.error = True
                return
            elif ctx.send_amount < config.Config.instance().get_rain_minimum():
                ctx.error = True
                await Messages.send_usage_dm(msg.author, RAIN_INFO)
                return
            # See if user exists in DB
            user = await User.get_user(msg.author)
            if user is None:
                await Messages.send_error_dm(msg.author, f"You should create an account with me first, send me `{config.Config.instance().command_prefix}help` to get started.")
                ctx.error = True
                return
            # Update name, if applicable
            await user.update_name(msg.author.name)
            ctx.user = user
        except AmountMissingException:
            await Messages.send_usage_dm(msg.author, RAIN_INFO)
            ctx.error = True
            return
        except AmountAmbiguousException:
            await Messages.send_error_dm(msg.author, "You can only specify 1 amount to send")
            ctx.error = True
            return

    @commands.command(aliases=RAIN_INFO.triggers)
    async def rain_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user
        send_amount = ctx.send_amount

        # Get active users
        active_users = await self.get_active(ctx, excluding=msg.author.id)
        if len(active_users) < Constants.RAIN_MIN_ACTIVE_COUNT:
            await Messages.send_error_dm(msg.author, f"Not enough users are active to rain - I need at least {Constants.RAIN_MIN_ACTIVE_COUNT}")
            return

        individual_send_amount = NumberUtil.truncate_digits(send_amount / len(active_users), max_digits=Env.precision_digits())
        if individual_send_amount < 0.01:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"Amount is too small to divide across {len(active_users)} users")
            return

        # See how much they need to make this tip.
        amount_needed = individual_send_amount * len(active_users)
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount_needed > available_balance:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount_needed} {Env.currency_symbol()}**")
            return

        # Make the transactions in the database
        tx_list = []
        task_list = []
        for u in active_users:
            tx = await Transaction.create_transaction_internal(
                sending_user=user,
                amount=individual_send_amount,
                receiving_user=u
            )
            tx_list.append(tx)
            task_list.append(
                Messages.send_basic_dm(
                    member=msg.guild.get_member(u.id),
                    message=f"You were tipped **{individual_send_amount} {Env.currency_symbol()}** by {msg.author.name.replace('`', '')}.\nUse `{config.Config.instance().command_prefix}mute {msg.author.id}` to disable notifications for this user.",
                    skip_dnd=True
                )
            )
        # Send DMs in the background
        asyncio.ensure_future(Utils.run_task_list(task_list))
        # Add reactions
        await Messages.add_tip_reaction(msg, amount_needed, rain=True)
        # Queue the actual sends
        for tx in tx_list:
            await TransactionQueue.instance().put(tx)
        # Add anti-spam
        await RedisDB.instance().set(f"rainspam{msg.author.id}", "as", expires=300)
        # Update stats
        stats: Stats = await user.get_stats(server_id=msg.guild.id)
        await stats.update_tip_stats(amount_needed)

    @staticmethod
    async def update_activity_stats(msg: discord.Message):
        """Update activity statistics for a user"""
        if ChannelUtil.is_private(msg.channel):
            return
        member = msg.author

        # Ignore if user doesnt have rain role
        has_rain_role = False
        rain_roles = config.Config.instance().get_rain_roles()
        if len(rain_roles) > 0:
            for role in member.roles:
                if role.id in rain_roles:
                    has_rain_role = True
                    break
            if not has_rain_role:
                return

        content_adjusted = Utils.emoji_strip(msg.content)
        if len(content_adjusted) == 0:
            return

        # Get user OBJ from redis if it exists, else create one
        user_key = f"activity:{msg.guild.id}:{msg.author.id}"
        active_stats = await RedisDB.instance().get(user_key)
        if active_stats is None:
            # Create stats and save
            active_stats = {
                'user_id': msg.author.id,
                'last_msg': datetime.datetime.utcnow().strftime('%m/%d/%Y %H:%M:%S'),
                'msg_count': 1
            }
            await RedisDB.instance().set(user_key, json.dumps(active_stats), expires=1800)
            return
        else:
            active_stats = json.loads(active_stats)

        # Ignore em if they've messaged too recently
        last_msg_dt = datetime.datetime.strptime(active_stats['last_msg'], '%m/%d/%Y %H:%M:%S')
        if last_msg_dt <= datetime.datetime.utcnow() - datetime.timedelta(minutes=2):
            return
        elif last_msg_dt > datetime.datetime.utcnow() - datetime.timedelta(minutes=15):
            # Deduct a point
            if active_stats['msg_count'] > 1:
                active_stats['msg_count'] -= 1
                await RedisDB.instance().set(user_key, json.dumps(active_stats), expires=1800)
        else:
            # add a point
            if active_stats['msg_count'] <= Constants.RAIN_MSG_REQUIREMENT * 2:
                active_stats['msg_count'] += 1
                await RedisDB.instance().set(user_key, json.dumps(active_stats), expires=1800)

    @staticmethod
    async def get_active(ctx: Context, excluding: int = 0) -> List[User]:
        """Return a list of active users"""
        msg = ctx.message
        redis = await RedisDB.instance().get_redis()

        # Get all activity stats from DB
        users_list = []
        async for key in redis.iscan(match=f"*activity:{msg.guild.id}*"):
            u = await redis.get(key)
            if u is not None:
                users_list.append(json.loads(u))

        if len(users_list) == 0:
            return []

        # Get IDs that meet requirements
        users_filtered = []
        for u in users_list:
            if u['user_id'] == excluding:
                continue
            elif u['msg_count'] >= Constants.RAIN_MSG_REQUIREMENT:
                users_filtered.append(u['user_id'])

        # Get only users in our database
        # TODO - consider tip banned, frozen
        return await User.filter(id__in=users_filtered).prefetch_related('account').all()

