import asyncio
import datetime
import logging
from typing import List

import discord
import rapidjson as json
from discord import app_commands
from discord.ext import commands

import config
from db.models.stats import Stats
from db.models.transaction import Transaction
from db.models.user import User
from db.redis import RedisDB
from models.command import CommandInfo
from models.constants import Constants
from tasks.transaction_queue import TransactionQueue
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages
from util.discord.resolver import require_user, validate_amount
from util.discord.users import resolve_member
from util.env import Env
from util.util import Utils

# Commands Documentation
RAIN_INFO = CommandInfo(
    triggers = ["brain" if Env.banano() else "nrain"],
    overview = "Distribute a tip amount amongst active users",
    details = "Distribute amount amongst active users." +
                f"\nExample: `/{'b' if Env.banano() else 'n'}rain 1000` will distribute 1000 {Env.currency_symbol()} between everyone who is active." +
                f"\n **minimum amount to rain: {config.Config.instance().get_rain_minimum()} {Env.currency_symbol()}**"
)

class RainCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Fires without the message content intent - only who/where/when matters here
        if message.author.bot:
            return
        if ChannelUtil.is_private(message.channel):
            return
        await self.update_activity_stats(message)

    @app_commands.command(name="brain" if Env.banano() else "nrain", description=RAIN_INFO.overview)
    @app_commands.describe(amount="Amount to distribute between all active users", anonymous="Hide your name from the recipients' notifications")
    @app_commands.guild_only()
    async def rain_cmd(self, interaction: discord.Interaction, amount: float, anonymous: bool = False):
        await interaction.response.defer()
        inv = await require_user(interaction)
        user = inv.user

        # Check anti-spam
        if not inv.god and await RedisDB.instance().exists(f"rainspam{interaction.user.id}"):
            await Messages.respond_error(interaction, "You can only rain once every 5 minutes")
            return
        validate_amount(amount, minimum=config.Config.instance().get_rain_minimum())

        # Get active users
        active_users = await self.get_active(interaction.guild_id, excluding=interaction.user.id)

        # Remove users who left the server or hold bad roles from eligibility
        to_remove = []
        for u in active_users:
            member = await resolve_member(interaction.guild, u.id)
            if member is None:
                to_remove.append(u)
                continue
            u.member = member
            for role in member.roles:
                if role.name.lower() in ['banano jail', 'muzzled']:
                    to_remove.append(u)
                    break

        for u in to_remove:
            active_users.remove(u)

        if len(active_users) < Constants.RAIN_MIN_ACTIVE_COUNT:
            await Messages.respond_error(interaction, f"Not enough users are active to rain - I need at least {Constants.RAIN_MIN_ACTIVE_COUNT} but there's only {len(active_users)} active bros")
            return

        individual_send_amount = Env.truncate_digits(amount / len(active_users), max_digits=Env.precision_digits())
        individual_send_amount_str = f"{individual_send_amount:.2f}" if Env.banano() else f"{individual_send_amount:.6f}"
        if individual_send_amount < Constants.TIP_MINIMUM:
            await Messages.respond_error(interaction, f"Amount is too small to divide across {len(active_users)} users")
            return

        amount_needed = Env.truncate_digits(individual_send_amount * len(active_users), max_digits=Env.precision_digits())
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount_needed > available_balance:
            await Messages.respond_error(interaction, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount_needed} {Env.currency_symbol()}**")
            return

        # Make the transactions in the database
        tx_list = []
        task_list = []
        for u in active_users:
            tx = await Transaction.create_transaction_internal_dbuser(
                sending_user=user,
                amount=individual_send_amount,
                receiving_user=u
            )
            tx_list.append(tx)
            if not await user.is_muted_by(u.id):
                if not anonymous:
                    notification = f"You were tipped **{individual_send_amount_str} {Env.currency_symbol()}** by {interaction.user.name.replace('`', '')}.\nUse `/mute` to disable notifications for this user."
                else:
                    notification = f"You were tipped **{individual_send_amount_str} {Env.currency_symbol()}** anonymously!"
                task_list.append(
                    Messages.send_basic_dm(
                        member=u.member,
                        message=notification,
                        skip_dnd=True
                    )
                )
        # Queue the actual sends
        for tx in tx_list:
            await TransactionQueue.instance().put(tx)
        # Send DMs in the background
        asyncio.ensure_future(Utils.run_task_list(task_list))
        await Messages.send_tip_line(interaction, amount_needed, interaction.user, f"**{len(tx_list)} active users** ({individual_send_amount_str} {Env.currency_symbol()} each)", rain=True)
        # Add anti-spam
        await RedisDB.instance().set(f"rainspam{interaction.user.id}", "as", expires=300)
        # Update stats
        stats: Stats = await user.get_stats(server_id=interaction.guild_id)
        if interaction.channel_id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(amount_needed)
        # DM creator
        await Messages.send_success_dm(interaction.user, f"You rained **{amount_needed} {Env.currency_symbol()}** to **{len(tx_list)} users**, they received **{individual_send_amount_str} {Env.currency_symbol()}** each.", header="Make it Rain")
        # Make the rainer auto-rain eligible
        await self.auto_rain_eligible(interaction.user, interaction.guild_id)

    @staticmethod
    async def auto_rain_eligible(member: discord.Member, guild_id: int):
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

        # Get user OBJ from redis if it exists, else create one
        user_key = f"activity:{guild_id}:{member.id}"
        active_stats = await RedisDB.instance().get(user_key)
        if active_stats is None:
            # Create stats and save
            active_stats = {
                'user_id': member.id,
                'last_msg': datetime.datetime.now(datetime.timezone.utc).strftime('%m/%d/%Y %H:%M:%S'),
                'msg_count': Constants.RAIN_MSG_REQUIREMENT * 2
            }
            await RedisDB.instance().set(user_key, json.dumps(active_stats), expires=1800)
            return
        else:
            active_stats = json.loads(active_stats)
            if active_stats['msg_count'] < Constants.RAIN_MSG_REQUIREMENT * 2:
                active_stats['msg_count'] = Constants.RAIN_MSG_REQUIREMENT * 2
            active_stats['last_msg'] = datetime.datetime.now(datetime.timezone.utc).strftime('%m/%d/%Y %H:%M:%S')
            await RedisDB.instance().set(user_key, json.dumps(active_stats), expires=1800)

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

        # Get user OBJ from redis if it exists, else create one
        user_key = f"activity:{msg.guild.id}:{msg.author.id}"
        active_stats = await RedisDB.instance().get(user_key)
        if active_stats is None:
            # Create stats and save
            active_stats = {
                'user_id': msg.author.id,
                'last_msg': datetime.datetime.now(datetime.timezone.utc).strftime('%m/%d/%Y %H:%M:%S'),
                'msg_count': 1
            }
            await RedisDB.instance().set(user_key, json.dumps(active_stats), expires=1800)
            return
        else:
            active_stats = json.loads(active_stats)

        # Ignore em if they've messaged too recently
        last_msg_dt = datetime.datetime.strptime(active_stats['last_msg'], '%m/%d/%Y %H:%M:%S')
        last_msg_dt = last_msg_dt.replace(tzinfo=datetime.timezone.utc)
        delta_s = (datetime.datetime.now(datetime.timezone.utc) - last_msg_dt).total_seconds()
        if 90 > delta_s:
            return
        elif delta_s > 1200:
            # Deduct a point
            if active_stats['msg_count'] > 1:
                active_stats['msg_count'] -= 1
            active_stats['last_msg'] = datetime.datetime.now(datetime.timezone.utc).strftime('%m/%d/%Y %H:%M:%S')
            await RedisDB.instance().set(user_key, json.dumps(active_stats), expires=1800)
        else:
            # add a point
            if active_stats['msg_count'] <= Constants.RAIN_MSG_REQUIREMENT * 2:
                active_stats['msg_count'] += 1
                active_stats['last_msg'] = datetime.datetime.now(datetime.timezone.utc).strftime('%m/%d/%Y %H:%M:%S')
                await RedisDB.instance().set(user_key, json.dumps(active_stats), expires=1800)
            else:
                # Reset key expiry
                active_stats['last_msg'] = datetime.datetime.now(datetime.timezone.utc).strftime('%m/%d/%Y %H:%M:%S')
                await RedisDB.instance().set(user_key, json.dumps(active_stats), expires=1800)

    @staticmethod
    async def get_active(guild_id: int, excluding: int = 0) -> List[User]:
        """Return a list of active users"""
        redis = await RedisDB.instance().get_redis()

        # Get all activity stats from DB
        users_list = []
        async for key in redis.scan_iter(match=f"*activity:{guild_id}*"):
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

        if len(users_filtered) < 1:
            return []

        # Get only users in our database
        return await User.filter(id__in=users_filtered, frozen=False, tip_banned=False).prefetch_related('account').all()
