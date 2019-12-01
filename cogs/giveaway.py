from aioredis_lock import RedisLock, LockTimeoutError
from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from util.env import Env
from util.discord.messages import Messages
from util.regex import RegexUtil, AmountMissingException
from db.models.account import Account
from db.models.giveaway import Giveaway
from db.models.user import User

import config
import discord
from util.discord.channel import ChannelUtil
from db.redis import RedisDB
from util.validators import Validators

# Commands Documentation
START_GIVEAWAY_INFO = CommandInfo(
    triggers = ["giveaway", "givearai"],
    overview = "Start a giveaway",
    details = "Start a giveaway with specified parameters" +
                f"\n**minimum amount: {config.Config.instance().get_giveaway_minimum()} {Env.currency_symbol()}**" +
                f"\n**minimum duration: {config.Config.instance().get_giveaway_min_duration()} minutes" +
                f"\n**maximum duration: {config.Config.instance().get_giveaway_max_duration()} minutes" +
                f"\n**Example:** `{config.Config.instance().command_prefix}giveaway 10 duration=30 fee=0.05`" + 
                f"\nWould start a giveaway of 10 {Env.currency_symbol()} that lasts 30 minutes with a 0.05 {Env.currency_symbol()} fee."
)

class GiveawayCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx: Context):
        ctx.error = False
        # Remove duplicate mentions
        ctx.message.mentions = set(ctx.message.mentions)
        # Only allow giveaway commands in public channels
        msg = ctx.message
        if ChannelUtil.is_private(msg.channel):
            ctx.error = True
            Messages.send_error_dm(msg.author, "You need to use giveaway commands in a public channel")
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
        if ctx.command.name not in 'giveaway_stats_cmd':
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

    @commands.command(aliases=START_GIVEAWAY_INFO.triggers)
    async def giveaway_cmd(self, ctx: Context):
        msg = ctx.message
        user = ctx.user

        # Check paused
        if await RedisDB.instance().is_paused():
            ctx.error = True
            await Messages.send_error_dm(msg.author, f"Transaction activity is currently suspended. I'll be back online soon!")
            return

        # Parse message
        split_content = msg.content.split(' ')
        cleaned_content = msg.content
        for split in split_content:
            if split.startswith('fee='):
                cleaned_content.replace(split, "")
                split = split.replace('fee=','').strip()
                if not split:
                    continue
                try:
                    fee = int(split)
                except ValueError as e:
                    await Messages.add_x_reaction(msg)
                    await Messages.send_usage_dm(msg.author, START_GIVEAWAY_INFO)
                    return
            elif split.startswith('duration='):
                cleaned_content.replace(split, "")
                split=split.replace('duration=','').strip()
                if not split:
                    continue
                try:
                    duration = int(split)
                    if not ctx.god and (duration < config.Config.instance().get_giveaway_min_duration() or duration > config.Config.instance().get_giveaway_max_duration()):
                        raise ValueError("Bad duration specified")
                except ValueError as e:
                    await Messages.add_x_reaction(msg)
                    await Messages.send_usage_dm(msg.author, START_GIVEAWAY_INFO)
                    return
        # Find giveaway amount
        try:
            giveaway_amount = RegexUtil.find_float(cleaned_content)
            if Validators.too_many_decimals(giveaway_amount):
                await Messages.send_error_dm(ctx.message.author, f"You are only allowed to use {Env.precision_digits()} digits after the decimal for giveaway amount.")
                ctx.error = True
                return
            elif fee > giveaway_amount * config.Config.instance().get_giveaway_max_fee_multiplier():
                await Messages.add_x_reaction(msg)
                await Messages.send_usage_dm(msg.author, START_GIVEAWAY_INFO)
                return
        except AmountMissingException:
            await Messages.add_x_reaction(msg)
            await Messages.send_usage_dm(msg.author, START_GIVEAWAY_INFO)
            return

        # See how much they need to make this tip.
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if giveaway_amount > available_balance:
            await Messages.add_x_reaction(ctx.message)
            await Messages.send_error_dm(msg.author, f"Your balance isn't high enough to start this giveaway. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{giveaway_amount} {Env.currency_symbol()}**")
            return

        try:
            # Lock this so concurrent giveaways can't be started/avoid race condition
            async with RedisLock(
                await RedisDB.instance().get_redis(),
                key=f"{Env.currency_symbol().lower()}giveawaylock:{msg.guild.id}",
                timeout=30,
                wait_timeout=30
            ) as lock:
                # See if giveaway already in progress
                active_giveaway = await Giveaway.get_active_giveaway(server_id=msg.guild.id)
                if active_giveaway is not None:
                    await Messages.add_x_reaction(msg)
                    await Messages.send_error_dm(msg.author, "There's already a giveaway in progress on this server")
                    return
                # Start giveaway
                gw = await Giveaway.start_giveaway_user(
                    server_id=msg.guild.id,
                    started_by=user,
                    amount=giveaway_amount,
                    entry_fee=fee,
                    duration=duration
                )
                # Create pending TX for this user
                # TODO
        except LockTimeoutError:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "I couldn't start a giveaway, maybe someone else beat you to it as there can only be 1 active at a time.")