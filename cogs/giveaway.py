from aioredis_lock import RedisLock, LockTimeoutError
from discord.ext import commands
from discord.ext.commands import Bot, Context
from tortoise.transactions import in_transaction
from models.command import CommandInfo
from util.env import Env
from util.discord.messages import Messages
from util.regex import RegexUtil, AmountMissingException
from db.models.account import Account
from db.models.giveaway import Giveaway
from db.models.transaction import Transaction
from db.models.user import User

import asyncio
import config
import datetime
import discord
import secrets
import random
from util.discord.channel import ChannelUtil
from db.redis import RedisDB
from tasks.transaction_queue import TransactionQueue
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

    async def role_check(self, msg: discord.Message) -> bool:
        "Return true if user can participate in giveaways, false otherwise"
        giveaway_roles = config.Config.instance().get_giveaway_roles()
        if len(giveaway_roles) == 0:
            return True # not configured to be restrictive
        can_participate = False
        for role in msg.author.roles:
            if role.id in giveaway_roles:
                can_participate = True
                break
        if not can_participate:
            role_names = []
            for role_id in giveaway_roles:
                role: discord.Role = msg.guild.get_role(role_id)
                if role is not None:
                    role_names.append(role.name)
            resp_str = ""
            for idx, name in enumerate(role_names):
                resp_str += name
                if idx != len(role_names) - 1:
                    resp_str += ", "
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"Sorry, only users with the following roles can participate in giveaways: {resp_str}")
            return False
        return True

    def format_giveaway_announcement(self, giveaway: Giveaway) -> discord.Embed:
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name="New Giveaway!", icon_url="https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/nano_logo.png")
        embed.description = f"{giveaway.started_by.name} has sponsored a giveaway of **{Env.raw_to_amount(int(giveaway.base_amount))} {Env.currency_name()}**!"
        fee = Env.raw_to_amount(giveaway.entry_fee)
        if fee > 0:
            embed.description+= f"\nThis giveaway has an entry fee of **{fee} {Env.currency_name()}**"
            embed.description+= f"\n`{config.Config.instance().command_prefix}ticket {fee}` - To enter this giveaway"
            embed.description+= f"\n`{config.Config.instance().command_prefix}{'donate' if Env.banano() else 'ntipgiveaway'} <amount>` - To increase the pot"
        else:
            embed.description+= f"\nThis giveaway is free to enter"
            embed.description+= f"\n`{config.Config.instance().command_prefix}ticket`"
            embed.description+= f"\n`{config.Config.instance().command_prefix}{'donate' if Env.banano() else 'ntipgiveaway'} <amount>` - To increase the pot"            
        duration = (datetime.datetime.utcnow() - giveaway.end_at).total_seconds()
        if duration < 60:
            embed.description += f"\nThis giveaway will end in **{int(duration)} seconds**"
        else:
            duration = duration // 60
            embed.description += f"\nThis giveaway will end in **{duration} minutes**"
        embed.description += "\nGood luck! \U0001F340"
        return embed


    async def start_giveaway_timer(self, giveaway: Giveaway):
        # Sleep for <giveaway duration> seconds
        delta = (giveaway.end_time - datetime.datetime.utcnow()).total_seconds()
        if delta > 0:
            await asyncio.sleep(delta)
        # End the giveaway
        # Get entries
        txs = await Transaction.filter(giveaway=giveaway).prefetch_related('user').all()
        users = []
        for tx in txs:
            if tx.user not in users:
                users.append(tx.user)
        # Pick winner
        random.shuffle(users, secrets.randbelow(100) / 100)
        winner = secrets.choice(users)
        # Finish this
        async with in_transaction() as conn:
            giveaway.ended_at = datetime.datetime.utcnow()
            giveaway.winning_user = winner
            await giveaway.save(using_db=conn, update_fields=['ended_at', 'winning_user'])
            # Update transactions
            winner_account = await winner.get_account()
            for tx in txs:
                tx.destination = winner_account
                await tx.save(using_db=conn, update_fields=['destination'])
        # Queue transactions
        tx_sum = 0
        for tx in txs:
            tx_sum += int(tx.amount)
            await TransactionQueue.instance().put(tx)
        # Announce winner
        main_channel = self.bot.get_channel(giveaway.started_in_channel)
        announce_channels = []
        if main_channel is not None:
            announce_channels.append(main_channel)
        for ch in config.Config.instance().get_giveaway_announce_channels():
            if ch == giveaway.started_in_channel:
                continue
            dch = self.bot.get_channel(giveaway.started_in_channel)
            if dch is not None:
                announce_channels.append(dch)

        ann_message = f"Congratulations! <@{winner.id}> was the winner of the giveaway!"
        ann_message+= f"\nThey have been sent **{Env.raw_to_amount(tx_sum)} {Env.currency_symbol()}**"
        if isinstance(giveaway.started_by, User):
            ann_message+= f"\nThanks to <@{giveaway.started_by.id}> for sponsoring this giveaway!"
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name="We have a winner!", icon_url="https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/nano_logo.png")
        embed.description = ann_message

        for ann in announce_channels:
            try:
                await ann.send(embed=embed)
            except Exception:
                pass

    @commands.command(aliases=START_GIVEAWAY_INFO.triggers)
    async def giveaway_cmd(self, ctx: Context):
        msg = ctx.message
        user = ctx.user

        # Check paused
        if await RedisDB.instance().is_paused():
            await Messages.send_error_dm(msg.author, f"Transaction activity is currently suspended. I'll be back online soon!")
            return

        # Check roles
        if not self.role_check(msg):
            return
        elif msg.channel.id in config.Config.instance().get_no_spam_channels():
            await Messages.send_error_dm(msg.author, f"You can't start giveaways in this channel")
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
            elif giveaway_amount < config.Config.instance().get_giveaway_minimum():
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
                async with in_transaction() as conn:
                    gw = await Giveaway.start_giveaway_user(
                        server_id=msg.guild.id,
                        started_by=user,
                        amount=giveaway_amount,
                        entry_fee=fee,
                        duration=duration,
                        started_in_channel=msg.channel.id,
                        conn=conn
                    )
                    # Create pending TX for this user
                    await Transaction.create_transaction_giveaway(
                        sending_user=user,
                        amount=giveaway_amount,
                        giveaway=gw,
                        conn=conn
                    )
                # Announce giveaway
                embed = self.format_giveaway_announcement(gw)
                await msg.channel.send(embed=embed)
                for ch in config.Config.instance().get_giveaway_announce_channels():
                    if ch != msg.channel.id:
                        channel = msg.guild.get_channel(ch)
                        if channel is not None:
                            try:
                                await channel.send(embed=embed)
                            except Exception:
                                pass
                # Start the timer
                asyncio.create_task(self.start_giveaway_timer(gw))
        except LockTimeoutError:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "I couldn't start a giveaway, maybe someone else beat you to it as there can only be 1 active at a time.")