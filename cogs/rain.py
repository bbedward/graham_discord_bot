
import discord
from discord.ext import commands
from discord.ext.commands import Bot, Context

from models.command import CommandInfo
from util.env import Env

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
        # TODO - check paused, frozen
        if ChannelUtil.is_private(ctx.message.channel):
            ctx.error = True
            return
        try:
            ctx.send_amount = RegexUtil.find_send_amounts(ctx.message.content)
            if Validators.too_many_decimals(ctx.send_amount):
                await Messages.send_error_dm(ctx.message.author, f"You are only allowed to use {Env.precision_digits()} digits after the decimal.")
                ctx.error = True
                return
            elif ctx.send_amount < config.Config.instance().get_rain_minimum():
                ctx.error = True
                await Messages.send_usage_dm(ctx.message.author, RAIN_INFO)
                return
            # See if user exists in DB
            user = await User.get_user(ctx.message.author)
            if user is None:
                await Messages.send_error_dm(ctx.message.author, f"You should create an account with me first, send me `{config.Config.instance().command_prefix}help` to get started.")
                ctx.error = True
                return
            # Update name, if applicable
            await user.update_name(ctx.message.author.name)
            ctx.user = user
        except AmountMissingException:
            await Messages.send_usage_dm(ctx.message.author, RAIN_INFO)
            ctx.error = True
            return
        except AmountAmbiguousException:
            await Messages.send_error_dm(ctx.message.author, "You can only specify 1 amount to send")
            ctx.error = True
            return

    @commands.command(aliases=RAIN_INFO.triggers)
    async def rain_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user
        await msg.channel.send(f"<@{msg.author.id}> I can't do that yet")

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

        # Update msg_count otherwise
        active_stats['msg_count'] += 1

        # Update DB
        await RedisDB.instance().set(user_key, json.dumps(active_stats), expires=1800)

    @staticmethod
    async def get_active(ctx: Context) -> List[User]:
        """Return a list of active users"""
        msg_minimum = 5
        msg = ctx.message
        redis = RedisDB.instance().get_redis()

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
            if u['msg_count'] >= msg_minimum:
                users_filtered.append(u['user_id'])

        # Get only users in our database
        return await User.filter(id__in=users_filtered).prefetch_related('account').all()

