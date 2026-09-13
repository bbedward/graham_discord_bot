import asyncio
import re
import secrets

import discord
from discord import app_commands
from discord.ext import commands

import cogs.rain as rain
import config
from db.models.stats import Stats
from db.models.transaction import Transaction
from db.redis import RedisDB
from models.command import CommandInfo
from models.constants import Constants
from tasks.transaction_queue import TransactionQueue
from util.discord.messages import Messages
from util.discord.resolver import require_user, validate_amount
from util.discord.users import resolve_member, resolve_user
from util.env import Env
from util.util import Utils

## Command documentation
TIP_INFO = CommandInfo(
    triggers = ["ban", "b"] if Env.banano() else ["ntip", "n"],
    overview = "Send a tip to mentioned users",
    details = f"Tip specified amount to mentioned user(s) (**minimum tip is {Constants.TIP_MINIMUM} {Constants.TIP_UNIT}**)" +
        "\nThe recipient(s) will be notified of your tip via private message" +
        "\nSuccessful tips will be deducted from your available balance immediately.\n" +
     f"Example: `/{'ban' if Env.banano() else 'ntip'} 2 @user1 @user2` would send 2 to user1 and 2 to user2"
)
TIPSPLIT_INFO = CommandInfo(
    triggers = ["bansplit", "bs"] if Env.banano() else ["ntipsplit", "ns"],
    overview = "Split a tip among mentioned users",
    details = f"Divide the specified amount between mentioned user(s) (**minimum tip is {Constants.TIP_MINIMUM} {Constants.TIP_UNIT}**)" +
        "\nThe recipient(s) will be notified of your tip via private message" +
        "\nSuccessful tips will be deducted from your available balance immediately.\n" +
     f"Example: `/{'bansplit' if Env.banano() else 'ntipsplit'} 2 @user1 @user2` would send 1 to user1 and 1 to user2"
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
    details = "Support the author of this bot (bbedward)"
)

MENTION_PATTERN = re.compile(r'<@!?(\d+)>')

def tip_notification(amount: float, sender: discord.abc.User) -> str:
    return f"You were tipped **{amount} {Env.currency_symbol()}** by {sender.name.replace('`', '')}.\nUse `/mute` to disable notifications for this user."

class TipsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def collect_recipients(self, interaction: discord.Interaction, users: list, more: str) -> list:
        recipients = []
        seen = set()
        candidates = [u for u in users if u is not None]
        if more is not None and interaction.guild is not None:
            for match in MENTION_PATTERN.finditer(more):
                member = await resolve_member(interaction.guild, int(match.group(1)))
                if member is not None:
                    candidates.append(member)
        for u in candidates:
            if u.bot or u.id == interaction.user.id or u.id in seen:
                continue
            seen.add(u.id)
            recipients.append(u)
        return recipients

    async def process_tip(self, interaction: discord.Interaction, individual_amount: float, recipients: list):
        inv = await require_user(interaction)
        user = inv.user

        amount_needed = individual_amount * len(recipients)
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount_needed > available_balance:
            await Messages.respond_error(interaction, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount_needed} {Env.currency_symbol()}**")
            return

        tx_list = []
        task_list = []
        for u in recipients:
            tx = await Transaction.create_transaction_internal(
                sending_user=user,
                amount=individual_amount,
                receiving_user=u
            )
            if tx is not None:
                tx_list.append(tx)
                if not await user.is_muted_by(u.id):
                    task_list.append(
                        Messages.send_basic_dm(
                            member=u,
                            message=tip_notification(individual_amount, interaction.user),
                            skip_dnd=True
                        )
                    )
        if len(tx_list) < 1:
            await Messages.respond_error(interaction, "No users you mentioned are eligible to receive tips.")
            return
        # Queue the actual sends
        for tx in tx_list:
            await TransactionQueue.instance().put(tx)
        # Send DMs in background, this is an attempt to avoid discord throttling us for sending too many at once
        asyncio.ensure_future(Utils.run_task_list(task_list))
        targets = ', '.join(u.mention for u in recipients)
        await Messages.send_tip_line(interaction, individual_amount * len(tx_list), interaction.user, targets)
        # Update stats
        stats: Stats = await user.get_stats(server_id=interaction.guild_id)
        if interaction.channel_id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(individual_amount * len(tx_list))

    @app_commands.command(name="ban" if Env.banano() else "ntip", description=TIP_INFO.overview)
    @app_commands.describe(amount="Amount to send to each user", to="The user to tip", more="Additional @mentions to tip the same amount")
    @app_commands.guild_only()
    async def tip_cmd(self, interaction: discord.Interaction, amount: float, to: discord.User,
                      to2: discord.User = None, to3: discord.User = None, to4: discord.User = None,
                      to5: discord.User = None, to6: discord.User = None, to7: discord.User = None,
                      to8: discord.User = None, to9: discord.User = None, more: str = None):
        await interaction.response.defer(ephemeral=True)
        validate_amount(amount, minimum=Constants.TIP_MINIMUM)
        recipients = await self.collect_recipients(interaction, [to, to2, to3, to4, to5, to6, to7, to8, to9], more)
        if len(recipients) < 1:
            await Messages.respond_error(interaction, "No users you mentioned are eligible to receive tips.")
            return
        await self.process_tip(interaction, amount, recipients)

    @app_commands.command(name="bansplit" if Env.banano() else "ntipsplit", description=TIPSPLIT_INFO.overview)
    @app_commands.describe(amount="Amount to divide between all mentioned users", to="The user to tip", more="Additional @mentions to split the amount with")
    @app_commands.guild_only()
    async def tipsplit_cmd(self, interaction: discord.Interaction, amount: float, to: discord.User,
                           to2: discord.User = None, to3: discord.User = None, to4: discord.User = None,
                           to5: discord.User = None, to6: discord.User = None, to7: discord.User = None,
                           to8: discord.User = None, to9: discord.User = None, more: str = None):
        await interaction.response.defer(ephemeral=True)
        validate_amount(amount, minimum=Constants.TIP_MINIMUM)
        recipients = await self.collect_recipients(interaction, [to, to2, to3, to4, to5, to6, to7, to8, to9], more)
        if len(recipients) < 1:
            await Messages.respond_error(interaction, "No users you mentioned are eligible to receive tips.")
            return
        individual_send_amount = Env.truncate_digits(amount / len(recipients), max_digits=Env.precision_digits())
        if individual_send_amount < Constants.TIP_MINIMUM:
            await Messages.respond_error(interaction, f"Tip amount too small, each user needs to receive at least {Constants.TIP_MINIMUM}. With your tip they'd only be getting {individual_send_amount}")
            return
        await self.process_tip(interaction, individual_send_amount, recipients)

    @app_commands.command(name="banrandom" if Env.banano() else "ntiprandom", description=TIPRANDOM_INFO.overview)
    @app_commands.describe(amount="Amount to tip a random active user")
    @app_commands.guild_only()
    async def tiprandom_cmd(self, interaction: discord.Interaction, amount: float):
        await interaction.response.defer(ephemeral=True)
        inv = await require_user(interaction)
        validate_amount(amount, minimum=Constants.TIPRANDOM_MINIMUM)
        user = inv.user

        # Check anti-spam
        if not inv.god and await RedisDB.instance().exists(f"tiprandomspam{interaction.guild_id}{interaction.user.id}"):
            await Messages.respond_error(interaction, "You can only tiprandom once every minute")
            return

        active_users = await rain.RainCog.get_active(interaction.guild_id, excluding=interaction.user.id)
        if len(active_users) < Constants.RAIN_MIN_ACTIVE_COUNT:
            await Messages.respond_error(interaction, f"There aren't enough active people to do a random tip. Only **{len(active_users)}** are active, but I'd like to see at least **{Constants.RAIN_MIN_ACTIVE_COUNT}**")
            return

        target_user = secrets.choice(active_users)

        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount > available_balance:
            await Messages.respond_error(interaction, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount} {Env.currency_symbol()}**")
            return

        tx = await Transaction.create_transaction_internal_dbuser(
            sending_user=user,
            amount=amount,
            receiving_user=target_user
        )
        await TransactionQueue.instance().put(tx)
        task_list = []
        if not await user.is_muted_by(target_user.id):
            target_member = await resolve_member(interaction.guild, target_user.id)
            if target_member is None:
                target_member = await resolve_user(self.bot, target_user.id)
            task_list.append(
                Messages.send_basic_dm(
                    member=target_member,
                    message=f"You were randomly selected and received **{amount} {Env.currency_symbol()}** from {interaction.user.name.replace('`', '')}.\nUse `/mute` to disable notifications for this user.",
                    skip_dnd=True
                )
            )
        task_list.append(
            Messages.send_basic_dm(
                member=interaction.user,
                message=f'"{target_user.name}" was the recipient of your random tip of {amount} {Env.currency_symbol()}'
            )
        )
        asyncio.ensure_future(Utils.run_task_list(task_list))
        await Messages.send_tip_line(interaction, amount, interaction.user, "a random active user \U0001F3B2")
        # anti spam
        await RedisDB.instance().set(f"tiprandomspam{interaction.guild_id}{interaction.user.id}", "as", expires=60)
        # Update stats
        stats: Stats = await user.get_stats(server_id=interaction.guild_id)
        if interaction.channel_id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(amount)

    @app_commands.command(name="banauthor" if Env.banano() else "tipauthor", description=TIPAUTHOR_INFO.overview)
    @app_commands.describe(amount="Amount to donate to the bot author")
    @app_commands.guild_only()
    async def tipauthor_cmd(self, interaction: discord.Interaction, amount: float):
        await interaction.response.defer(ephemeral=True)
        inv = await require_user(interaction)
        validate_amount(amount, minimum=Constants.TIP_MINIMUM)
        user = inv.user

        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount > available_balance:
            await Messages.respond_error(interaction, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount} {Env.currency_symbol()}**")
            return

        tx = await Transaction.create_transaction_external(
            sending_user=user,
            amount=amount,
            destination=Env.donation_address()
        )
        await TransactionQueue.instance().put(tx)
        await Messages.send_public(interaction, f"\U00002611\U0001F618❤ **{interaction.user.display_name}** donated to the bot author. Thank you!", ack="Thank you ❤")
        # Update stats
        stats: Stats = await user.get_stats(server_id=interaction.guild_id)
        if interaction.channel_id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(amount)
