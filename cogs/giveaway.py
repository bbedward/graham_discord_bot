import asyncio
import datetime
import logging
import secrets

import discord
from discord import app_commands
from discord.ext import commands
from redis.exceptions import LockError
from tortoise.transactions import in_transaction

import config
from db.models.giveaway import Giveaway
from db.models.stats import Stats
from db.models.transaction import Transaction
from db.models.user import User
from db.redis import RedisDB
from models.command import CommandInfo
from models.constants import Constants
from tasks.transaction_queue import TransactionQueue
from util.discord.messages import Messages
from util.discord.resolver import require_user, resolve, validate_amount
from util.discord.users import resolve_member, resolve_user
from util.env import Env
from util.util import Utils

TICKET_COMMAND = "/ticket"
DONATE_COMMAND = f"/{'donate' if Env.banano() else 'ntipgiveaway'}"

# Commands Documentation
START_GIVEAWAY_INFO = CommandInfo(
    triggers = ["giveaway", "givearai"],
    overview = "Start a giveaway",
    details = "Start a giveaway with specified parameters" +
                f"\n**minimum amount: {config.Config.instance().get_giveaway_minimum()} {Env.currency_symbol()}**" +
                f"\n**minimum duration: {config.Config.instance().get_giveaway_min_duration()} minutes" +
                f"\n**maximum duration: {config.Config.instance().get_giveaway_max_duration()} minutes" +
                "\n**Example:** `/giveaway 10 duration:30 fee:0.05`" +
                f"\nWould start a giveaway of 10 {Env.currency_symbol()} that lasts 30 minutes with a 0.05 {Env.currency_symbol()} fee."
)
TICKET_INFO = CommandInfo(
    triggers = ["ticket", "enter", "e"],
    overview = "Enter the currently active giveaway",
    details = "Enter the currently active giveaway, if there is one." +
                f"\nFor giveaways without a fee, simply use `{TICKET_COMMAND}`"
                f"\nFor giveaways with a fee, use `{TICKET_COMMAND} <fee>`"
                f"\n**In DM, giveaway_id is required**"
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
                f"\nExample: `{DONATE_COMMAND} 1` - Donate 1 {Env.currency_symbol()} to the current or next giveaway"
                f"\nWhen **{config.Config.instance().get_giveaway_auto_minimum()} {Env.currency_symbol()}** is donated, a giveaway will automatically begin."
)

class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
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

    async def role_check(self, interaction: discord.Interaction, member: discord.Member, guild: discord.Guild) -> bool:
        "Return true if user can participate in giveaways, false otherwise"
        giveaway_roles = config.Config.instance().get_giveaway_roles()
        if len(giveaway_roles) == 0:
            return True # not configured to be restrictive
        can_participate = any(role.id in giveaway_roles for role in member.roles)
        if not can_participate:
            role_names = []
            for role_id in giveaway_roles:
                role: discord.Role = guild.get_role(role_id)
                if role is not None:
                    role_names.append(role.name)
            await Messages.respond_error(interaction, f"Sorry, only users with the following roles can participate in giveaways: {', '.join(role_names)}")
            return False
        return True

    async def punish_spam(self, interaction: discord.Interaction, god: bool, message: str) -> None:
        if god:
            await Messages.respond_error(interaction, message)
            return
        spam = await RedisDB.instance().get(f"ticketspam:{interaction.user.id}")
        spam = int(spam) if spam is not None else 0
        await RedisDB.instance().set(f"ticketspam:{interaction.user.id}", str(spam + 1), expires=3600)
        await Messages.respond_error(interaction, message)

    async def get_ticket_spam(self, interaction: discord.Interaction, god: bool) -> int:
        if god:
            return 0
        spam = await RedisDB.instance().get(f"ticketspam:{interaction.user.id}")
        return int(spam) if spam is not None else 0

    def format_giveaway_announcement(self, giveaway: Giveaway, amount: int = None) -> discord.Embed:
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name=f"New Giveaway! #{giveaway.id}", icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
        embed.description = f"<@{giveaway.started_by.id if not giveaway.started_by_bot else self.bot.user.id}> has sponsored a giveaway of **{Env.raw_to_amount(int(giveaway.base_amount if amount is None else amount))} {Env.currency_name()}**!\n"
        fee = Env.raw_to_amount(int(giveaway.entry_fee))
        if fee > 0:
            embed.description+= f"\nThis giveaway has an entry fee of **{fee} {Env.currency_name()}**"
            embed.description+= f"\n`{TICKET_COMMAND} {fee}` - To enter this giveaway"
        else:
            embed.description+= f"\nThis giveaway is free to enter:"
            embed.description+= f"\n`{TICKET_COMMAND}` - To enter this giveaway"
        embed.description+= f"\n`{DONATE_COMMAND} <amount>` - To increase the pot"
        duration = (Utils.as_utc(giveaway.end_at) - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
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
        delta = (Utils.as_utc(giveaway.end_at) - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
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
        winner = secrets.choice(users)
        # Calculate total winning amount
        tx_sum = 0
        for tx in txs:
            tx_sum += int(tx.amount)
        # Finish this
        async with in_transaction() as conn:
            giveaway.ended_at = datetime.datetime.now(datetime.timezone.utc)
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
        member = await resolve_user(self.bot, winner.id)
        if member is not None:
            await Messages.send_success_dm(member, f"Congratulations! **You've won giveaway #{giveaway.id}**! I've sent you **{Env.raw_to_amount(tx_sum)} {Env.currency_symbol()}**")
        # Cleanup
        try:
            self.giveaway_ids.remove(giveaway.id)
        except ValueError:
            pass

    @app_commands.command(name="giveaway", description=START_GIVEAWAY_INFO.overview)
    @app_commands.describe(amount="Amount to give away", duration="Duration in minutes", fee="Entry fee")
    @app_commands.guild_only()
    async def giveaway_cmd(self, interaction: discord.Interaction, amount: float, duration: int, fee: float = 0.0):
        await interaction.response.defer()
        inv = await require_user(interaction)
        user = inv.user

        # Check roles
        if not await self.role_check(interaction, interaction.user, interaction.guild):
            return
        elif interaction.channel_id in config.Config.instance().get_no_spam_channels():
            await Messages.respond_error(interaction, "You can't start giveaways in this channel")
            return

        fee = abs(fee)
        duration = abs(duration)
        if not inv.god and (duration < config.Config.instance().get_giveaway_min_duration() or duration > config.Config.instance().get_giveaway_max_duration()):
            await Messages.respond_error(interaction, f"Duration must be between {config.Config.instance().get_giveaway_min_duration()} and {config.Config.instance().get_giveaway_max_duration()} minutes.")
            return
        validate_amount(amount, minimum=config.Config.instance().get_giveaway_minimum())
        if fee > amount * config.Config.instance().get_giveaway_max_fee_multiplier():
            await Messages.respond_error(interaction, "The fee is too high compared to the giveaway amount.")
            return

        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount > available_balance:
            await Messages.respond_error(interaction, f"Your balance isn't high enough to start this giveaway. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount} {Env.currency_symbol()}**")
            return

        try:
            # Lock this so concurrent giveaways can't be started/avoid race condition
            async with (await RedisDB.instance().get_redis()).lock(
                f"{Env.currency_symbol().lower()}giveawaylock:{interaction.guild_id}",
                timeout=30,
                blocking_timeout=30,
                raise_on_release_error=False
            ):
                # See if giveaway already in progress
                active_giveaway = await Giveaway.get_active_giveaway(server_id=interaction.guild_id)
                if active_giveaway is not None:
                    await Messages.respond_error(interaction, "There's already a giveaway in progress on this server")
                    return
                # Start giveaway
                async with in_transaction() as conn:
                    gw = await Giveaway.start_giveaway_user(
                        server_id=interaction.guild_id,
                        started_by=user,
                        amount=amount,
                        entry_fee=fee,
                        duration=duration,
                        started_in_channel=interaction.channel_id,
                        conn=conn
                    )
                    # Create pending TX for this user
                    await Transaction.create_transaction_giveaway(
                        sending_user=user,
                        amount=amount,
                        giveaway=gw,
                        conn=conn
                    )
                    # Update stats
                    stats: Stats = await user.get_stats(server_id=interaction.guild_id)
                    await stats.update_tip_stats(amount)
                # Announce giveaway
                embed = self.format_giveaway_announcement(gw)
                try:
                    await interaction.followup.send(embed=embed)
                except Exception:
                    pass
                for ch in config.Config.instance().get_giveaway_announce_channels():
                    if ch != interaction.channel_id:
                        channel = interaction.guild.get_channel(ch)
                        if channel is not None:
                            try:
                                await channel.send(embed=embed)
                            except Exception:
                                pass
                # Start the timer
                asyncio.create_task(self.start_giveaway_timer(gw))
        except LockError:
            await Messages.respond_error(interaction, "I couldn't start a giveaway, maybe someone else beat you to it as there can only be 1 active at a time.")

    @app_commands.command(name="ticket", description=TICKET_INFO.overview)
    @app_commands.describe(fee="Amount to pay the entry fee, for giveaways that have one", giveaway_id="The giveaway number to enter (required in DM)")
    async def ticket_cmd(self, interaction: discord.Interaction, fee: float = 0.0, giveaway_id: int = None):
        await interaction.response.defer(ephemeral=True)
        inv = await resolve(interaction, check_paused=False)
        user = inv.user

        is_private = interaction.guild is None
        if is_private and giveaway_id is None:
            await Messages.respond_error(interaction, "You need to specify `giveaway_id` when entering from DM.")
            return

        # See if they've been spamming
        spam = await self.get_ticket_spam(interaction, inv.god)
        if spam >= 3:
            await Messages.respond_error(interaction, "You're temporarily banned from entering giveaways")
            return

        # Get active giveaway
        if giveaway_id is None:
            gw = await Giveaway.get_active_giveaway(server_id=interaction.guild_id)
        else:
            gw = await Giveaway.get_active_giveaway_by_id(id=giveaway_id)

        if gw is None:
            await RedisDB.instance().set(f"ticketspam:{interaction.user.id}", str(spam + 1), expires=3600)
            await Messages.respond_error(interaction, "There aren't any active giveaways to enter.")
            return

        # Check roles
        if is_private:
            guild = self.bot.get_guild(gw.server_id)
            if guild is None:
                await Messages.respond_error(interaction, "Something went wrong, ask my master for help")
                return
            member = await resolve_member(guild, interaction.user.id)
            if member is None:
                await Messages.respond_error(interaction, "You're not a member of that server")
                return
        else:
            guild = interaction.guild
            member = interaction.user

        if not await self.role_check(interaction, member, guild):
            return

        # There is an active giveaway, enter em if not already entered.
        # Check and write under a per-user lock - every duplicate entry row becomes a real send
        try:
            async with (await RedisDB.instance().get_redis()).lock(
                f"{Env.currency_symbol().lower()}giveawayentrylock:{gw.id}:{user.id}",
                timeout=30,
                blocking_timeout=10,
                raise_on_release_error=False
            ):
                active_tx = await Transaction.filter(giveaway__id=gw.id, sending_user__id=user.id).order_by('created_at').first()
                if active_tx is not None and int(gw.entry_fee) == 0:
                    await Messages.respond_error(interaction, "You've already entered this giveaway.")
                    return
                elif active_tx is None:
                    paid_already = 0
                else:
                    paid_already = int(active_tx.amount)

                if paid_already >= int(gw.entry_fee) and int(gw.entry_fee) > 0:
                    await Messages.respond_error(interaction, "You've already entered this giveaway.")
                    return

                # Enter em
                fee_raw = int(gw.entry_fee) - paid_already
                fee_needed = Env.raw_to_amount(fee_raw)
                # Check balance if fee is > 0
                if fee_needed > 0:
                    if fee <= 0:
                        await Messages.respond_error(interaction, f"This giveaway has a fee, you need to specify the amount to enter. `{TICKET_COMMAND} {fee_needed}`")
                        return
                    if fee < fee_needed:
                        await Messages.respond_error(interaction, f"This giveaway has a fee of {fee_needed} {Env.currency_symbol()}. The amount you specified isn't enough to cover the entry fee")
                        return
                    available_balance = Env.raw_to_amount(await user.get_available_balance())
                    if fee_needed > available_balance:
                        await RedisDB.instance().set(f"ticketspam:{interaction.user.id}", str(spam + 1), expires=3600)
                        await Messages.respond_error(interaction, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this entry would cost you **{fee_needed} {Env.currency_symbol()}**")
                        return
                # Top up any existing entry row rather than inserting a second one
                if active_tx is not None:
                    async with in_transaction() as conn:
                        active_tx.amount = str(paid_already + fee_raw)
                        await active_tx.save(update_fields=['amount'], using_db=conn)
                else:
                    await Transaction.create_transaction_giveaway(
                        user,
                        fee_needed,
                        gw
                    )
        except LockError:
            await Messages.respond_error(interaction, "I'm still processing your last entry, try again in a moment.")
            return
        await Messages.respond_success(interaction, f"You've successfully been entered into giveaway #{gw.id}")

    @app_commands.command(name="giveawaystats", description=GIVEAWAYSTATS_INFO.overview)
    @app_commands.guild_only()
    async def giveawaystats_cmd(self, interaction: discord.Interaction):
        inv = await resolve(interaction, check_paused=False)

        # Punish them for trying to do this command in a no spam channel
        if interaction.channel_id in config.Config.instance().get_no_spam_channels() and not inv.god:
            await self.punish_spam(interaction, inv.god, "You can't view giveaway stats in this channel")
            return

        # Respond privately if the channel was asked recently
        ephemeral = await RedisDB.instance().exists(f'giveawaystatsspam:{interaction.channel_id}')
        if not ephemeral:
            await RedisDB.instance().set(f'giveawaystatsspam:{interaction.channel_id}', 'as', expires=60)

        gw = await Giveaway.get_active_giveaway(server_id=interaction.guild_id)
        pending_gw = None
        if gw is None:
            pending_gw = await Giveaway.get_pending_bot_giveaway(server_id=interaction.guild_id)
            if pending_gw is None:
                await Messages.respond_error(interaction, "There are no active giveaways")
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
                embed.description+= f"\n`{TICKET_COMMAND} {fee}` - To enter this giveaway"
            else:
                embed.description+= f"\nThis giveaway is free to enter:"
                embed.description+= f"\n`{TICKET_COMMAND}` - To enter this giveaway"
            embed.description+= f"\n`{DONATE_COMMAND} <amount>` - To increase the pot"
            duration = (Utils.as_utc(gw.end_at) - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
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

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name="winners", description=WINNERS_INFO.overview)
    @app_commands.guild_only()
    async def winners_cmd(self, interaction: discord.Interaction):
        inv = await resolve(interaction, check_paused=False)

        # Punish them for trying to do this command in a no spam channel
        if interaction.channel_id in config.Config.instance().get_no_spam_channels() and not inv.god:
            await self.punish_spam(interaction, inv.god, "You can't view giveaway stats in this channel")
            return

        ephemeral = await RedisDB.instance().exists(f'winnersspam:{interaction.channel_id}')
        if not ephemeral:
            await RedisDB.instance().set(f'winnersspam:{interaction.channel_id}', 'as', expires=60)

        # Get list
        winners = await Giveaway.filter(server_id=interaction.guild_id, winning_user_id__not_isnull=True, ended_at__not_isnull=True).order_by('-ended_at').prefetch_related('winning_user').limit(10).all()
        if len(winners) == 0:
            await Messages.respond_error(interaction, "There haven't been any giveaways on this server yet")
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

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name="donate" if Env.banano() else "ntipgiveaway", description=TIPGIVEAWAY_INFO.overview)
    @app_commands.describe(amount="Amount to donate to the current or next giveaway")
    @app_commands.guild_only()
    async def tipgiveaway_cmd(self, interaction: discord.Interaction, amount: float):
        await interaction.response.defer(ephemeral=True)
        inv = await resolve(interaction, check_paused=False)
        user = inv.user

        # Check roles
        if not await self.role_check(interaction, interaction.user, interaction.guild):
            return

        # Punish them for trying to do this command in a no spam channel
        if interaction.channel_id in config.Config.instance().get_no_spam_channels() and not inv.god:
            await self.punish_spam(interaction, inv.god, "You can't donate to the giveaway in this channel")
            return

        if amount < Constants.TIP_MINIMUM:
            await Messages.respond_error(interaction, f"Minimum tip amount is {Constants.TIP_MINIMUM}")
            return

        # Get active giveaway
        gw = await Giveaway.get_active_giveaway(server_id=interaction.guild_id)
        if gw is None:
            # get bot-pending giveaway or create one
            gw = await Giveaway.get_pending_bot_giveaway(server_id=interaction.guild_id)

        if gw is None:
            try:
                # Initiate the bot giveaway with a lock to avoid race condition
                async with (await RedisDB.instance().get_redis()).lock(
                    f"{Env.currency_symbol().lower()}giveawaylock:{interaction.guild_id}",
                    timeout=30,
                    blocking_timeout=30,
                    raise_on_release_error=False
                ):
                    # See if giveaway already in progress
                    should_create = False
                    active_giveaway = await Giveaway.get_active_giveaway(server_id=interaction.guild_id)
                    if active_giveaway is None:
                        bot_giveaway = await Giveaway.get_pending_bot_giveaway(server_id=interaction.guild_id)
                        if bot_giveaway is None:
                            should_create = True
                    if should_create:
                        # Start giveaway
                        async with in_transaction() as conn:
                            gw = await Giveaway.start_giveaway_bot(
                                server_id=interaction.guild_id,
                                entry_fee=config.Config.instance().get_giveaway_auto_fee(),
                                started_in_channel=interaction.channel_id,
                                conn=conn
                            )
            except LockError:
                gw = await Giveaway.get_pending_bot_giveaway(server_id=interaction.guild_id)
                if gw is None:
                    await Messages.respond_error(interaction, "I was unable to process your donation, try again later!")
                    return

        # Check balance
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount > available_balance:
            if not inv.god:
                spam = await self.get_ticket_spam(interaction, inv.god)
                await RedisDB.instance().set(f"ticketspam:{interaction.user.id}", str(spam + 1), expires=3600)
            await Messages.respond_error(interaction, "Your balance isn't high enough to complete this tip.")
            return

        # See if they already contributed, under the same per-user lock as ticket_cmd
        already_entered = False
        try:
            async with (await RedisDB.instance().get_redis()).lock(
                f"{Env.currency_symbol().lower()}giveawayentrylock:{gw.id}:{user.id}",
                timeout=30,
                blocking_timeout=10,
                raise_on_release_error=False
            ):
                user_tx = await Transaction.filter(giveaway__id=gw.id, sending_user__id=user.id).order_by('created_at').first()
                async with in_transaction() as conn:
                    if user_tx is not None:
                        if int(user_tx.amount) >= int(gw.entry_fee):
                            already_entered=True
                        user_tx.amount = str(int(user_tx.amount) + Env.amount_to_raw(amount))
                        await user_tx.save(update_fields=['amount'], using_db=conn)
                    else:
                        user_tx = await Transaction.create_transaction_giveaway(
                            user,
                            amount,
                            gw,
                            conn=conn
                        )
        except LockError:
            await Messages.respond_error(interaction, "I'm still processing your last donation, try again in a moment.")
            return

        if gw.end_at is None:
            if not already_entered and int(user_tx.amount) >= int(gw.entry_fee):
                await Messages.respond_success(interaction, f"With your generous donation of {Env.raw_to_amount(int(user_tx.amount))} {Env.currency_symbol()} I have reserved your spot for giveaway #{gw.id}!")
            else:
                await Messages.respond_success(interaction, f"Your generous donation of {Env.raw_to_amount(int(user_tx.amount))} {Env.currency_symbol()} will help support giveaway #{gw.id}!")
            # See if we should start this giveaway, and start it if so
            giveaway_sum_raw = 0
            for tx in await Transaction.filter(giveaway=gw):
                giveaway_sum_raw += int(tx.amount)
            giveaway_sum = Env.raw_to_amount(giveaway_sum_raw)
            if giveaway_sum >= config.Config.instance().get_giveaway_auto_minimum():
                # start giveaway
                # re-fetch latest version
                gw = await Giveaway.get_pending_bot_giveaway(server_id=interaction.guild_id)
                if gw is not None:
                    gw.end_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=config.Config.instance().get_giveaway_auto_duration())
                    gw.started_in_channel = interaction.channel_id
                    async with in_transaction() as conn:
                        await gw.save(update_fields=['end_at', 'started_in_channel'], using_db=conn)
                    # Announce giveaway
                    embed = self.format_giveaway_announcement(gw, amount=giveaway_sum_raw)
                    for ch in [interaction.channel_id] + config.Config.instance().get_giveaway_announce_channels():
                        channel = interaction.guild.get_channel(ch)
                        if channel is not None:
                            try:
                                await channel.send(embed=embed)
                            except Exception:
                                pass
                    # Start the timer
                    asyncio.create_task(self.start_giveaway_timer(gw))
        else:
            if not already_entered and int(user_tx.amount) >= int(gw.entry_fee):
                await Messages.respond_success(interaction, f"With your generous donation of {amount} {Env.currency_symbol()} I have entered you into giveaway #{gw.id}!")
            else:
                await Messages.respond_success(interaction, f"Your generous donation of {amount} {Env.currency_symbol()} will help support giveaway #{gw.id}!")

        # Update stats
        stats: Stats = await user.get_stats(server_id=interaction.guild_id)
        if interaction.channel_id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(amount)

    @app_commands.command(name="ticketstatus", description=TICKETSTATUS_INFO.overview)
    async def ticketstatus_cmd(self, interaction: discord.Interaction):
        inv = await resolve(interaction, check_paused=False)
        user = inv.user

        # If private, see what servers they are part of
        guilds = None
        if interaction.guild is None:
            guilds = []
            for g in self.bot.guilds:
                if await resolve_member(g, interaction.user.id) is not None:
                    guilds.append(g)
            if len(guilds) == 0:
                return

        # See if they've been spamming
        spam = await self.get_ticket_spam(interaction, inv.god)
        if spam >= 3:
            await Messages.respond_error(interaction, "You're temporarily banned from entering giveaways")
            return

        # Get active giveaway(s) - public channel
        if guilds is None:
            gw = await Giveaway.get_active_giveaway(server_id=interaction.guild_id)

            if gw is None:
                await RedisDB.instance().set(f"ticketspam:{interaction.user.id}", str(spam + 1), expires=3600)
                await Messages.respond_error(interaction, "There aren't any active giveaways.")
                return

            # Get their active giveaway transaction
            active_tx = await Transaction.filter(giveaway__id=gw.id, sending_user__id=user.id).first()
            if active_tx is None:
                if int(gw.entry_fee) > 0:
                    fee_converted = Env.raw_to_amount(int(gw.entry_fee))
                    response = f"There is a fee of **{fee_converted} {Env.currency_symbol()}**!\n"
                    response+= f"Use `{TICKET_COMMAND} {fee_converted}` to pay the fee and enter"
                else:
                    response = f"This giveaway is free to enter\n"
                    response+= f"Use `{TICKET_COMMAND}` to enter."
            else:
                needed = int(gw.entry_fee) - int(active_tx.amount)
                if needed <= 0:
                    response = f"You're already entered into this giveaway"
                else:
                    fee_converted = Env.raw_to_amount(int(gw.entry_fee))
                    paid_converted = Env.raw_to_amount(int(active_tx.amount))
                    response = f"There is a fee of **{fee_converted} {Env.currency_symbol()}**! You've donated **{paid_converted} {Env.currency_symbol()}** but that's not enough to enter!\n"
                    response+= f"Use `{TICKET_COMMAND} {Env.format_float(fee_converted - paid_converted)}` to pay the fee and enter"

            # Build response
            embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
            embed.set_author(name=f"Giveaway #{gw.id} is active!", icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
            embed.description = response

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        # Get active giveaways (private channel)
        gws = await Giveaway.get_active_giveaways(server_ids=[g.id for g in guilds])
        if gws is None or len(gws) == 0:
            await RedisDB.instance().set(f"ticketspam:{interaction.user.id}", str(spam + 1), expires=3600)
            await Messages.respond_error(interaction, "There aren't any active giveaways.")
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
                    response+= f"Use `{TICKET_COMMAND} {fee_converted}` with giveaway_id {gw.id} to pay the fee and enter\n"
                else:
                    response+= f"This giveaway is free to enter\n"
                    response+= f"Use `{TICKET_COMMAND}` with giveaway_id {gw.id} to enter.\n"
            else:
                needed = int(gw.entry_fee) - int(active_tx.amount)
                if needed <= 0:
                    response+= f"You're already entered into this giveaway"
                else:
                    fee_converted = Env.raw_to_amount(int(gw.entry_fee))
                    paid_converted = Env.raw_to_amount(int(active_tx.amount))
                    response+= f"There is a fee of **{fee_converted} {Env.currency_symbol()}**! You've donated **{paid_converted} {Env.currency_symbol()}** but that's not enough to enter!\n"
                    response+= f"Use `{TICKET_COMMAND} {Env.format_float(fee_converted - paid_converted)}` with giveaway_id {gw.id} to pay the fee and enter\n"

        # Build response
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name=f"Here are the active giveaways!", icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
        embed.description = response

        await interaction.response.send_message(embed=embed, ephemeral=True)
