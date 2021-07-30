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
import logging
import secrets
import random
from util.discord.channel import ChannelUtil
from db.redis import RedisDB
from tasks.transaction_queue import TransactionQueue
from util.validators import Validators
from util.util import Utils
from models.constants import Constants

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
TICKET_INFO = CommandInfo(
    triggers = ["ticket", "enter", "e"],
    overview = "Enter the currently active giveaway",
    details = "Enter the currently active giveaway, if there is one." +
                f"\nFor giveaways without a fee, simply use `{config.Config.instance().command_prefix}ticket`"
                f"\nFor giveaways with a fee, simply use `{config.Config.instance().command_prefix}ticket <fee>`"
                f"\n**In private channels, id is required** example: `{config.Config.instance().command_prefix}ticket <fee> id=3` for giveaway #3"
)
TICKETSTATUS_INFO = CommandInfo(
    triggers = ["ticketstatus", "ts"],
    overview = "Check entry status",
    details = "See if you are entered into the current giveaway, if there is one"
)
GIVEAWAYSTATS_INFO = CommandInfo(
    triggers = ["giveawaystats", "gs"],
    overview = "View stats related to the currently active giveaway",
    details = "View time left, number of entries, and other information about the currently active giveaway"
)
WINNERS_INFO = CommandInfo(
    triggers = ["winners"],
    overview = "View recent giveaway winners",
    details = "View the 10 most recent giveaways winners as well as the amount they've won."
)
TIPGIVEAWAY_INFO = CommandInfo(
    triggers = ["donate", "do"] if Env.banano() else ["ntipgiveaway", "ntg"],
    overview = "Donate to giveaway",
    details = "Donate to the currently active giveaway to increase the pot, or donate to towards starting a giveaway automatically." +
                f"\nExample: `{config.Config.instance().command_prefix}{'donate' if Env.banano() else 'ntipgiveaway'} 1` - Donate 1 {Env.currency_symbol()} to the current or next giveaway"
                f"\nWhen **{config.Config.instance().get_giveaway_auto_minimum()} {Env.currency_symbol()}** is donated, a giveaway will automatically begin."
)

class GiveawayCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.logger = logging.getLogger()
        self.giveaway_ids = []

    @commands.Cog.listener()
    async def on_ready(self):
        # Get active giveaways
        self.logger.info("Checking for active giveaways")
        for guild in self.bot.guilds:
            gw = await Giveaway.get_active_giveaway(server_id=guild.id)
            if gw is not None:
                self.logger.info(f"Resuming giveaway {gw.id}")
                asyncio.create_task(self.start_giveaway_timer(gw))

    async def cog_before_invoke(self, ctx: Context):
        ctx.error = False
        # Remove duplicate mentions
        ctx.message.mentions = set(ctx.message.mentions)
        # Only allow giveaway commands in public channels
        msg = ctx.message
        if ChannelUtil.is_private(msg.channel) and ctx.command.name not in ['ticketstatus_cmd', 'ticket_cmd']:
            ctx.error = True
            await Messages.send_error_dm(msg.author, "You need to use giveaway commands in a public channel")
            return
        else:
            # Determine if user is admin
            ctx.god = msg.author.id in config.Config.instance().get_admin_ids()
            if not ctx.god:
                ctx.admin = False
                for g in self.bot.guilds:
                    member = g.get_member(msg.author.id)
                    if member is not None:
                        for role in member.roles:
                            if role.id in config.Config.instance().get_admin_roles():
                                ctx.admin = True
                                break
                    if ctx.admin:
                        break
            else:
                ctx.admin = True
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

    def format_giveaway_announcement(self, giveaway: Giveaway, amount: int = None) -> discord.Embed:
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name=f"New Giveaway! #{giveaway.id}", icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
        embed.description = f"<@{giveaway.started_by.id if not giveaway.started_by_bot else self.bot.user.id}> has sponsored a giveaway of **{Env.raw_to_amount(int(giveaway.base_amount if amount is None else amount))} {Env.currency_name()}**!\n"
        fee = Env.raw_to_amount(int(giveaway.entry_fee))
        if fee > 0:
            embed.description+= f"\nThis giveaway has an entry fee of **{fee} {Env.currency_name()}**"
            embed.description+= f"\n`{config.Config.instance().command_prefix}ticket {fee}` - To enter this giveaway"
            embed.description+= f"\n`{config.Config.instance().command_prefix}{'donate' if Env.banano() else 'ntipgiveaway'} <amount>` - To increase the pot"
        else:
            embed.description+= f"\nThis giveaway is free to enter:"
            embed.description+= f"\n`{config.Config.instance().command_prefix}ticket` - To enter this giveaway"
            embed.description+= f"\n`{config.Config.instance().command_prefix}{'donate' if Env.banano() else 'ntipgiveaway'} <amount>` - To increase the pot"            
        duration = (giveaway.end_at - datetime.datetime.utcnow()).total_seconds()
        if duration < 60:
            embed.description += f"\n\nThis giveaway will end in **{int(duration)} seconds**"
        else:
            duration = duration // 60
            embed.description += f"\n\nThis giveaway will end in **{int(duration)} minutes**"
        embed.description += "\nGood luck! \U0001F340"
        return embed

    async def start_giveaway_timer(self, giveaway: Giveaway):
        # Ensure timer not already started
        if giveaway.id in self.giveaway_ids:
            return
        self.giveaway_ids.append(giveaway.id)
        # Sleep for <giveaway duration> seconds
        delta = (giveaway.end_at - datetime.datetime.utcnow()).total_seconds()
        if delta > 0:
            await asyncio.sleep(delta)
        # End the giveaway
        # Get entries
        txs = await Transaction.filter(giveaway=giveaway).prefetch_related('sending_user').all()
        users = []
        for tx in txs:
            if tx.sending_user not in users and int(tx.amount) >= int(giveaway.entry_fee):
                users.append(tx.sending_user)
        # Pick winner
        random.shuffle(users, Utils.random_float)
        winner = secrets.choice(users)
        # Calculate total winning amount
        tx_sum = 0
        for tx in txs:
            tx_sum += int(tx.amount)
        # Finish this
        async with in_transaction() as conn:
            giveaway.ended_at = datetime.datetime.utcnow()
            giveaway.winning_user = winner
            giveaway.final_amount = str(tx_sum)
            await giveaway.save(using_db=conn, update_fields=['ended_at', 'winning_user_id', 'final_amount'])
            # Update transactions
            winner_account = await winner.get_address()
            for tx in txs:
                if tx.amount == '0':
                    await tx.delete()
                else:
                    tx.destination = winner_account
                    tx.receiving_user = winner
                    await tx.save(using_db=conn, update_fields=['receiving_user_id', 'destination'])
        # Queue transactions
        for tx in txs:
            await TransactionQueue.instance().put(tx)
        # Announce winner
        main_channel = self.bot.get_channel(giveaway.started_in_channel)
        announce_channels = []
        if main_channel is not None:
            announce_channels.append(main_channel)
        for ch in config.Config.instance().get_giveaway_announce_channels():
            if ch == giveaway.started_in_channel:
                continue
            dch = self.bot.get_channel(ch)
            if dch is not None:
                announce_channels.append(dch)

        ann_message = f"Congratulations! <@{winner.id}> was the winner of the giveaway!"
        ann_message+= f"\nThey have been sent **{Env.raw_to_amount(tx_sum)} {Env.currency_symbol()}**"
        if isinstance(giveaway.started_by, User):
            ann_message+= f"\n\nThanks to <@{giveaway.started_by.id}> for sponsoring this giveaway!"
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name="We have a winner!", icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
        embed.description = ann_message

        for ann in announce_channels:
            try:
                await ann.send(embed=embed)
            except Exception:
                pass
        # DM the winner
        member = self.bot.get_user(winner.id)
        if member is not None:
            await Messages.send_success_dm(member, f"Congratulations! **You've won giveaway #{giveaway.id}**! I've sent you **{Env.raw_to_amount(tx_sum)} {Env.currency_symbol()}**")
        # Cleanup
        try:
            self.giveaway_ids.remove(giveaway.id)
        except ValueError:
            pass

    @commands.command(aliases=START_GIVEAWAY_INFO.triggers)
    async def giveaway_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user

        # Check paused
        if await RedisDB.instance().is_paused():
            await Messages.send_error_dm(msg.author, f"Transaction activity is currently suspended. I'll be back online soon!")
            return

        # Check roles
        if not await self.role_check(msg):
            return
        elif msg.channel.id in config.Config.instance().get_no_spam_channels():
            await Messages.send_error_dm(msg.author, f"You can't start giveaways in this channel")
            return

        if 'fee=' not in msg.content or 'duration=' not in msg.content:
            await Messages.send_usage_dm(msg.author, START_GIVEAWAY_INFO)
            await Messages.add_x_reaction(msg)
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
                    fee = abs(float(split))
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
                    duration = abs(int(split))
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
                    # Update stats
                    stats: Stats = await user.get_stats(server_id=msg.guild.id)
                    await stats.update_tip_stats(giveaway_amount)
                # Announce giveaway
                embed = self.format_giveaway_announcement(gw)
                try:
                    await msg.channel.send(embed=embed)
                except Exception:
                    pass
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

    @commands.command(aliases=TICKET_INFO.triggers)
    async def ticket_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user
        author = msg.author
        content = msg.content

        is_private = ChannelUtil.is_private(msg.channel)
        id=None

        if is_private:
            if 'id=' not in msg.content:
                await Messages.send_usage_dm(msg.author, TICKET_INFO)
                await Messages.add_x_reaction(msg)
                return            

            # Parse message
            split_content = msg.content.split(' ')
            cleaned_content = msg.content
            for split in split_content:
                if split.startswith('id='):
                    cleaned_content.replace(split, "")
                    split = split.replace('id=','').strip()
                    if not split:
                        continue
                    try:
                        id = int(split)
                    except ValueError as e:
                        await Messages.add_x_reaction(msg)
                        await Messages.send_usage_dm(msg.author, TICKET_INFO)
                        return

        # See if they've been spamming
        redis_key = f"ticketspam:{msg.author.id}"
        if not ctx.god:
            spam = await RedisDB.instance().get(redis_key)
            if spam is not None:
                spam = int(spam)
                if spam >= 3:
                    await Messages.send_error_dm(msg.author, "You're temporarily banned from entering giveaways")
                    await Messages.delete_message_if_ok(msg)
                    return
            else:
                spam = 0
        else:
            spam = 0

        # Get active giveaway
        if id is None:
            gw = await Giveaway.get_active_giveaway(server_id=msg.guild.id)
        else:
            gw = await Giveaway.get_active_giveaway_by_id(id=id)

        if gw is None:
            await Messages.send_error_dm(msg.author, "There aren't any active giveaways to enter.")
            await Messages.delete_message_if_ok(msg)
            # Block ticket spam
            await RedisDB.instance().set(f"ticketspam:{msg.author.id}", str(spam + 1), expires=3600)
            return

        # Check roles
        if is_private:
            guild = self.bot.get_guild(gw.server_id)
            if guild is None:
                await Messages.send_error_dm(msg.author, "Something went wrong, ask my master for help")
                return
            member = guild.get_member(msg.author.id)
            if member is None:
                await "You're not a member of that server"
                return
            msg.author = member
    
        if not await self.role_check(msg):
            return

        # There is an active giveaway, enter em if not already entered.
        active_tx = await Transaction.filter(giveaway__id=gw.id, sending_user__id=user.id).first()
        if active_tx is not None and int(gw.entry_fee) == 0:
            await Messages.send_error_dm(msg.author, "You've already entered this giveaway.")
            await Messages.delete_message_if_ok(msg)
            return
        elif active_tx is None:
            paid_already = 0
        else:
            paid_already = int(active_tx.amount)
    
        if paid_already >= int(gw.entry_fee) and int(gw.entry_fee) > 0:
            await Messages.send_error_dm(msg.author, "You've already entered this giveaway.")
            await Messages.delete_message_if_ok(msg)
            return

        # Enter em
        fee_raw = int(gw.entry_fee) - paid_already
        fee = Env.raw_to_amount(fee_raw)
        # Check balance if fee is > 0
        if fee > 0:
            try:
                amount = RegexUtil.find_float(msg.content)
                if amount < fee:
                    await Messages.send_error_dm(msg.author, f"This giveaway has a fee of {fee} {Env.currency_symbol()}. The amount you specified isn't enough to cover the entry fee")
                    await Messages.delete_message_if_ok(msg)
                    return
            except AmountMissingException:
                await Messages.send_error_dm(msg.author, f"This giveaway has a fee, you need to specify the amount to enter. `{config.Config.instance().command_prefix}ticket {fee}`")
                await Messages.delete_message_if_ok(msg)
                return
            available_balance = Env.raw_to_amount(await user.get_available_balance())
            if fee > available_balance:
                await Messages.add_x_reaction(ctx.message)
                await Messages.send_error_dm(msg.author, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this entry would cost you **{fee} {Env.currency_symbol()}**")
                await Messages.delete_message_if_ok(msg)
                await RedisDB.instance().set(f"ticketspam:{msg.author.id}", str(spam + 1), expires=3600)
                return
        await Transaction.create_transaction_giveaway(
            user,
            fee,
            gw
        )
        await Messages.send_success_dm(msg.author, f"You've successfully been entered into giveaway #{gw.id}")
        await Messages.delete_message_if_ok(msg)
        return

    @commands.command(aliases=GIVEAWAYSTATS_INFO.triggers)
    async def giveawaystats_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user

        as_dm = False

        # Punish them for trying to do this command in a no spam channel
        if msg.channel.id in config.Config.instance().get_no_spam_channels():
            redis_key = f"ticketspam:{msg.author.id}"
            if not ctx.god:
                spam = await RedisDB.instance().get(redis_key)
                if spam is not None:
                    spam = int(spam)
                else:
                    spam = 0
                await Messages.add_x_reaction(msg)
                await Messages.send_error_dm(msg.author, "You can't view giveaway stats in this channel")
                await RedisDB.instance().set(f"ticketspam:{msg.author.id}", str(spam + 1), expires=3600)
                return

        if not as_dm:
            # Check spamming of this command
            if len(config.Config.instance().get_giveaway_no_delete_channels()) > 0 and msg.channel.id not in config.Config.instance().get_giveaway_no_delete_channels():
                as_dm = True
            if await RedisDB.instance().exists(f'giveawaystatsspam:{msg.channel.id}'):
                as_dm = True
            else:
                await RedisDB.instance().set(f'giveawaystatsspam:{msg.channel.id}', 'as', expires=60)

        gw = await Giveaway.get_active_giveaway(server_id=msg.guild.id)
        pending_gw = None
        if gw is None:
            pending_gw = await Giveaway.get_pending_bot_giveaway(server_id=msg.guild.id)
            if pending_gw is None:
                if as_dm:
                    await Messages.send_error_dm(msg.author, "There are no active giveaways")
                else:
                    await Messages.send_error_public(msg.channel, "There are no active giveaways")
                await Messages.delete_message_if_ok(msg)
                return
            else:
                gw = pending_gw

        # Get stats
        transactions = await gw.get_transactions()
        entries = 0
        donors = 0
        amount = 0
        for tx in transactions:
            tx: Transaction = tx
            if int(tx.amount) >= int(gw.entry_fee):
                entries +=  1
            donors += 1
            amount += Env.raw_to_amount(int(tx.amount))

        # Format stats message
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name=f"Giveaway #{gw.id}", icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
        fee = Env.raw_to_amount(int(gw.entry_fee))
        if pending_gw is None:
            embed.description = f"There are **{entries} entries** to win **{Env.truncate_digits(amount, max_digits=Env.precision_digits())} {Env.currency_symbol()}**\n"
            if fee > 0:
                embed.description+= f"\nThis giveaway has an entry fee of **{fee} {Env.currency_name()}**"
                embed.description+= f"\n`{config.Config.instance().command_prefix}ticket {fee}` - To enter this giveaway"
                embed.description+= f"\n`{config.Config.instance().command_prefix}{'donate' if Env.banano() else 'ntipgiveaway'} <amount>` - To increase the pot"
            else:
                embed.description+= f"\nThis giveaway is free to enter:"
                embed.description+= f"\n`{config.Config.instance().command_prefix}ticket` - To enter this giveaway"
                embed.description+= f"\n`{config.Config.instance().command_prefix}{'donate' if Env.banano() else 'ntipgiveaway'} <amount>` - To increase the pot"            
            duration = (gw.end_at - datetime.datetime.utcnow()).total_seconds()
            if duration < 60:
                embed.description += f"\n\nThis giveaway will end in **{int(duration)} seconds**"
            else:
                duration = duration // 60
                embed.description += f"\n\nThis giveaway will end in **{int(duration)} minutes**"
            embed.description += "\nGood luck! \U0001F340"
        else:
            embed.description = f"This giveaway hasn't started yet\n"
            embed.description += f"\nSo far **{donors}** people have donated to this giveaway and **{entries}** people are eligible to win."
            embed.description += f"\n**{Env.truncate_digits(config.Config.instance().get_giveaway_auto_minimum() - amount, max_digits=Env.precision_digits())} {Env.currency_symbol()}** more needs to be donated to start this giveaway."

        try:
            if as_dm:
                await msg.author.send(embed=embed)
                if msg.channel.id in config.Config.instance().get_giveaway_no_delete_channels():
                    await msg.add_reaction('\u2709')
            else:
                await msg.channel.send(embed=embed)
        except Exception:
            pass
        await Messages.delete_message_if_ok(msg)

    @commands.command(aliases=WINNERS_INFO.triggers)
    async def winners_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user

        as_dm = False

        # Punish them for trying to do this command in a no spam channel
        if msg.channel.id in config.Config.instance().get_no_spam_channels():
            redis_key = f"ticketspam:{msg.author.id}"
            if not ctx.god:
                spam = await RedisDB.instance().get(redis_key)
                if spam is not None:
                    spam = int(spam)
                else:
                    spam = 0
                await Messages.add_x_reaction(msg)
                await Messages.send_error_dm(msg.author, "You can't view giveaway stats in this channel")
                await RedisDB.instance().set(f"ticketspam:{msg.author.id}", str(spam + 1), expires=3600)
                return

        if not as_dm:
            # Check spamming of this command
            if await RedisDB.instance().exists(f'winnersspam:{msg.channel.id}'):
                as_dm = True
            else:
                await RedisDB.instance().set(f'winnersspam:{msg.channel.id}', 'as', expires=60)

        # Get list
        winners = await Giveaway.filter(server_id=msg.guild.id, winning_user_id__not_isnull=True, ended_at__not_isnull=True).order_by('-ended_at').prefetch_related('winning_user').limit(10).all()

        if len(winners) == 0:
            await msg.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "There haven't been any giveaways on this server yet")
            return

        response_msg = "```"
        # Get biggest amount to adjust the padding
        biggest_num = 0
        for winner in winners:
            winning_amount = Env.raw_to_amount(int(winner.final_amount))
            length = len(f"{Env.format_float(winning_amount)} {Env.currency_symbol()}")
            if length > biggest_num:
                biggest_num = length
        for rank, winner in enumerate(winners, start=1):
            adj_rank = str(rank) if rank >= 10 else f" {rank}"
            user_name = winner.winning_user.name
            amount_str = f"{Env.format_float(Env.raw_to_amount(int(winner.final_amount)))} {Env.currency_symbol()}".ljust(biggest_num)
            response_msg += f"{adj_rank}. {amount_str} - won by {user_name}\n" 
        response_msg += "```"

        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name=f"Here are the last {len(winners)} giveaway winners \U0001F44F", icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
        embed.description = response_msg

        if not as_dm:
            await msg.channel.send(f"<@{msg.author.id}>", embed=embed)    
        else:
            await msg.author.send(embed=embed)
            await msg.add_reaction('\u2709')

    @commands.command(aliases=TIPGIVEAWAY_INFO.triggers)
    async def tipgiveaway_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user

        # Check roles
        if not await self.role_check(msg):
            return

        # Punish them for trying to do this command in a no spam channel
        if msg.channel.id in config.Config.instance().get_no_spam_channels():
            redis_key = f"ticketspam:{msg.author.id}"
            if not ctx.god:
                spam = await RedisDB.instance().get(redis_key)
                if spam is not None:
                    spam = int(spam)
                else:
                    spam = 0
                await Messages.add_x_reaction(msg)
                await Messages.send_error_dm(msg.author, "You can't view donate to the giveaway in this channel")
                await RedisDB.instance().set(f"ticketspam:{msg.author.id}", str(spam + 1), expires=3600)
                await Messages.delete_message_if_ok(msg)
                return

        # Get their tip amount
        try:
            tip_amount = RegexUtil.find_float(msg.content)
            if tip_amount < Constants.TIP_MINIMUM:
                await Messages.send_error_dm(msg.author, f"Minimum tip amount if {Constants.TIP_MINIMUM}")
                await Messages.delete_message_if_ok(msg)
                return
        except AmountMissingException:
            await Messages.send_usage_dm(msg.author, TIPGIVEAWAY_INFO)
            await Messages.delete_message_if_ok(msg)
            return

        # Get active giveaway
        gw = await Giveaway.get_active_giveaway(server_id=msg.guild.id)
        if gw is None:
            # get bot-pending giveaway or create one
            gw = await Giveaway.get_pending_bot_giveaway(server_id=msg.guild.id)

        if gw is None:
            try:
                # Initiate the bot giveaway with a lock to avoid race condition
                # Lock this so concurrent giveaways can't be started/avoid race condition
                async with RedisLock(
                    await RedisDB.instance().get_redis(),
                    key=f"{Env.currency_symbol().lower()}giveawaylock:{msg.guild.id}",
                    timeout=30,
                    wait_timeout=30
                ) as lock:
                    # See if giveaway already in progress
                    should_create = False
                    active_giveaway = await Giveaway.get_active_giveaway(server_id=msg.guild.id)
                    if active_giveaway is None:
                        bot_giveaway = await Giveaway.get_pending_bot_giveaway(server_id=msg.guild.id)
                        if bot_giveaway is None:
                            should_create = True
                    if should_create:
                        # Start giveaway
                        async with in_transaction() as conn:
                            gw = await Giveaway.start_giveaway_bot(
                                server_id=msg.guild.id,
                                entry_fee=config.Config.instance().get_giveaway_auto_fee(),
                                started_in_channel=msg.channel.id,
                                conn=conn
                            )
            except LockTimeoutError:
                gw = await Giveaway.get_pending_bot_giveaway(server_id=msg.guild.id)
                if gw is None:
                    await Messages.send_error_dm(msg.author, "I was unable to process your donation, try again alter!")
                    await Messages.delete_message_if_ok(msg)
                    return

        # Check balance
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if tip_amount > available_balance:
            if not ctx.god:
                redis_key = f"ticketspam:{msg.author.id}"
                spam = await RedisDB.instance().get(redis_key)
                if spam is not None:
                    spam = int(spam)
                else:
                    spam = 0
                await RedisDB.instance().set(f"ticketspam:{msg.author.id}", str(spam + 1), expires=3600)
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "Your balance isn't high enough to complete this tip.")
            await Messages.delete_message_if_ok(msg)
            return

        # See if they already contributed
        user_tx = await Transaction.filter(giveaway__id=gw.id, sending_user__id=user.id).first()
        already_entered = False
        async with in_transaction() as conn:
            if user_tx is not None:
                if int(user_tx.amount) >= int(gw.entry_fee):
                    already_entered=True
                user_tx.amount = str(int(user_tx.amount) + Env.amount_to_raw(tip_amount))
                await user_tx.save(update_fields=['amount'], using_db=conn)
            else:
                user_tx = await Transaction.create_transaction_giveaway(
                    user,
                    tip_amount,
                    gw,
                    conn=conn
                )
    
        if gw.end_at is None:
            if not already_entered and int(user_tx.amount) >= int(gw.entry_fee):
                await Messages.send_success_dm(msg.author, f"With your generous donation of {Env.raw_to_amount(int(user_tx.amount))} {Env.currency_symbol()} I have reserved your spot for giveaway #{gw.id}!")
            else:
                await Messages.send_success_dm(msg.author, f"Your generous donation of {Env.raw_to_amount(int(user_tx.amount))} {Env.currency_symbol()} will help support giveaway #{gw.id}!")
            # See if we should start this giveaway, and start it if so
            # TODO - We should use the DB SUM() function but,we store it as a VarChar and tortoise-orm currently doesn't support casting
            giveaway_sum_raw = 0
            for tx in await Transaction.filter(giveaway=gw):
                giveaway_sum_raw += int(tx.amount)
            giveaway_sum = Env.raw_to_amount(giveaway_sum_raw)
            if giveaway_sum >= config.Config.instance().get_giveaway_auto_minimum():
                # start giveaway
                # re-fetch latest version
                gw = await Giveaway.get_pending_bot_giveaway(server_id=msg.guild.id)
                if gw is not None:
                    gw.end_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=config.Config.instance().get_giveaway_auto_duration())
                    gw.started_in_channel = msg.channel.id
                    async with in_transaction() as conn:
                        await gw.save(update_fields=['end_at', 'started_in_channel'], using_db=conn)
                    # Announce giveaway
                    embed = self.format_giveaway_announcement(gw, amount=giveaway_sum_raw)
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
        else:
            if not already_entered and int(user_tx.amount) >= int(gw.entry_fee):
                await Messages.send_success_dm(msg.author, f"With your generous donation of {tip_amount} {Env.currency_symbol()} I have entered you into giveaway #{gw.id}!")
            else:
                await Messages.send_success_dm(msg.author, f"Your generous donation of {tip_amount} {Env.currency_symbol()} will help support giveaway #{gw.id}!")

        if msg.channel.id in config.Config.instance().get_giveaway_no_delete_channels():
            await Messages.add_tip_reaction(msg, tip_amount)

        await Messages.delete_message_if_ok(msg)
        # Update stats
        stats: Stats = await user.get_stats(server_id=msg.guild.id)
        if msg.channel.id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(tip_amount)

    @commands.command(aliases=TICKETSTATUS_INFO.triggers)
    async def ticketstatus_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user
        author = msg.author
        content = msg.content

        # If private, see what servers they are part of
        guilds = None
        if ChannelUtil.is_private(msg.channel):
            guilds = []
            for g in self.bot.guilds:
                if g.get_member(msg.author.id) is not None:
                    guilds.append(g)
            if len(guilds) == 0:
                return

        # See if they've been spamming
        redis_key = f"ticketspam:{msg.author.id}"
        if not ctx.god:
            spam = await RedisDB.instance().get(redis_key)
            if spam is not None:
                spam = int(spam)
                if spam >= 3:
                    await Messages.send_error_dm(msg.author, "You're temporarily banned from entering giveaways")
                    await Messages.delete_message(msg)
                    return
            else:
                spam = 0
        else:
            spam = 0

        # Get active giveaway(s) - public channel
        if guilds == None:
            gw = await Giveaway.get_active_giveaway(server_id=msg.guild.id)

            if gw is None:
                await Messages.send_error_dm(msg.author, "There aren't any active giveaways.")
                await Messages.delete_message(msg)
                # Block ticket spam
                await RedisDB.instance().set(f"ticketspam:{msg.author.id}", str(spam + 1), expires=3600)
                return

            # Get their active giveaway transaction
            active_tx = await Transaction.filter(giveaway__id=gw.id, sending_user__id=user.id).first()
            response = None
            if active_tx is None:
                if int(gw.entry_fee) > 0:
                    fee_converted = Env.raw_to_amount(int(gw.entry_fee))
                    response = f"There is a fee of **{fee_converted} {Env.currency_symbol()}**!\n"
                    response+= f"Use `{config.Config.instance().command_prefix}ticket {fee_converted}` to pay the fee and enter"
                else:
                    response = f"This giveaway is free to enter\n"
                    response+= f"Use `{config.Config.instance().command_prefix}ticket` to enter."
            else:
                needed = int(gw.entry_fee) - int(active_tx.amount)
                if needed <= 0:
                    response = f"You're already entered into this giveaway"
                else:
                    fee_converted = Env.raw_to_amount(int(gw.entry_fee))
                    paid_converted = Env.raw_to_amount(int(active_tx.amount))
                    response = f"There is a fee of **{fee_converted} {Env.currency_symbol()}**! You've donated **{paid_converted} {Env.currency_symbol()}** but that's not enough to enter!\n"
                    response+= f"Use `{config.Config.instance().command_prefix}ticket {Env.format_float(fee_converted - paid_converted)}` to pay the fee and enter"

            # Build response
            embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
            embed.set_author(name=f"Giveaway #{gw.id} is active!", icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
            embed.description = response

            await msg.author.send(embed=embed)
            await Messages.delete_message(msg)
            return
        # Get active giveaways (private channel)
        gws = await Giveaway.get_active_giveaways(server_ids=[g.id for g in guilds])
        if gws is None or len(gws) == 0:
            await Messages.send_error_dm(msg.author, "There aren't any active giveaways.")
            await Messages.delete_message(msg)
            # Block ticket spam
            await RedisDB.instance().set(f"ticketspam:{msg.author.id}", str(spam + 1), expires=3600)
            return

        # Get their active giveaway transaction
        response = None
        for gw in gws:
            active_tx = await Transaction.filter(giveaway__id=gw.id, sending_user__id=user.id).first()
            response = f"**Giveaway #{gw.id}**\n" if response is None else f"**Giveaway #{gw.id}**:\n"
            if active_tx is None:
                if int(gw.entry_fee) > 0:
                    fee_converted = Env.raw_to_amount(int(gw.entry_fee))
                    response+= f"There is a fee of **{fee_converted} {Env.currency_symbol()}**!\n"
                    response+= f"Use `{config.Config.instance().command_prefix}ticket {fee_converted} id={gw.id}` to pay the fee and enter\n"
                else:
                    response+= f"This giveaway is free to enter\n"
                    response+= f"Use `{config.Config.instance().command_prefix}ticket id={gw.id}` to enter.\n"
            else:
                needed = int(gw.entry_fee) - int(active_tx.amount)
                if needed <= 0:
                    response+= f"You're already entered into this giveaway"
                else:
                    fee_converted = Env.raw_to_amount(int(gw.entry_fee))
                    paid_converted = Env.raw_to_amount(int(active_tx.amount))
                    response+= f"There is a fee of **{fee_converted} {Env.currency_symbol()}**! You've donated **{paid_converted} {Env.currency_symbol()}** but that's not enough to enter!\n"
                    response+= f"Use `{config.Config.instance().command_prefix}ticket {Env.format_float(fee_converted - paid_converted)} id={gw.id}` to pay the fee and enter\n"

        # Build response
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name=f"Here are the active giveaways!", icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
        embed.description = response

        await msg.author.send(embed=embed)
        await Messages.delete_message(msg)
