import logging

import discord
from discord import app_commands
from discord.ext import commands
from tortoise.transactions import in_transaction

import config
from db.models.stats import Stats
from db.models.user import User
from db.redis import RedisDB
from models.command import CommandInfo
from util.discord.messages import Messages
from util.discord.paginator import Entry, Page, Paginator
from util.discord.resolver import require_admin
from util.discord.users import resolve_member
from util.env import Env

## Command documentation
PAUSE_INFO = CommandInfo(
    triggers = ["pause"],
    overview = "Pause all transaction activity",
    details = "All users will be unable to withdraw or tip while the bot is paused."
)
RESUME_INFO = CommandInfo(
    triggers = ["resume", "unpause"],
    overview = "Resume all transaction activity",
    details = "Everybody can tip again when it's unpaused :)"
)
FREEZE_INFO = CommandInfo(
    triggers = ["freeze"],
    overview = "Freeze the mentioned users",
    details = "Completely freeze the mentioned user's account"
)
DEFROST_INFO = CommandInfo(
    triggers = ["defrost", "unfreeze"],
    overview = "Un-freeze a user",
    details = "Give user access to his account again"
)
FROZEN_INFO = CommandInfo(
    triggers = ["frozen"],
    overview = "Get a list of frozen users",
    details = "Lists all the users that have been frozen."
)
TIPBAN_INFO = CommandInfo(
    triggers = ["tipban"],
    overview = "Tip ban the mentioned users",
    details = "Mentioned users will not be able to receive tips anymore"
)
TIPUNBAN_INFO = CommandInfo(
    triggers = ["tipunban"],
    overview = "Unban mentioned users",
    details = "Users will be able to receive tips again."
)
TIPBANNED_INFO = CommandInfo(
    triggers = ["tipbanned"],
    overview = "Get a list of banned users",
    details = "Lists all the users that have been tip banned."
)
STATSBAN_INFO = CommandInfo(
    triggers = ["statsban"],
    overview = "Stats ban the mentioned users",
    details = "Mentioned users will not be considered in statistics anymore."
)
STATSUNBAN_INFO = CommandInfo(
    triggers = ["statsunban"],
    overview = "Unban mentioned users",
    details = "Users will be considered for stats again"
)
STATSBANNED_INFO = CommandInfo(
    triggers = ["statsbanned"],
    overview = "Get a list of stats banned users",
    details = "Lists all the users that have been stats banned."
)
DECREASETIPS_INFO = CommandInfo(
    triggers = ["decreasetips"],
    overview = "Decrease tip stat total",
    details = f"`/decreasetips @bbedward 1000` - Reduce users tip count by 1000 {Env.currency_name()}"
)
INCREASETIPS_INFO = CommandInfo(
    triggers = ["increasetips"],
    overview = "Increase tip stat total",
    details = f"`/increasetips @bbedward 1000` - Increase users tip count by 1000 {Env.currency_name()}"
)

async def is_protected_target(user: discord.User, guild: discord.Guild) -> bool:
    if user.id in config.Config.instance().get_admin_ids():
        return True
    if guild is None:
        return False
    member = await resolve_member(guild, user.id)
    if member is None:
        return False
    admin_roles = config.Config.instance().get_admin_roles()
    return any(role.id in admin_roles for role in member.roles)

def banned_user_pages(banned: list, title: str, undo_command: str) -> list:
    entries = [Entry(f"{user_id}:{name}", f"Undo with `/{undo_command}` and their ID: {user_id}") for user_id, name in banned]
    description = f"Use `/{undo_command}` to undo"
    return [Page(entries=entries[i:i + 15], author=title, description=description) for i in range(0, len(entries), 15)]

class AdminCog(commands.Cog):
    """Commands for admins only"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger()

    @app_commands.command(name="pause", description=PAUSE_INFO.overview)
    @app_commands.default_permissions(manage_guild=True)
    async def pause_cmd(self, interaction: discord.Interaction):
        await require_admin(interaction)
        await RedisDB.instance().pause()
        await Messages.respond_success(interaction, "Transaction activity is now suspended ⏸")

    @app_commands.command(name="resume", description=RESUME_INFO.overview)
    @app_commands.default_permissions(manage_guild=True)
    async def resume_cmd(self, interaction: discord.Interaction):
        await require_admin(interaction)
        await RedisDB.instance().resume()
        await Messages.respond_success(interaction, "Transaction activity is no longer suspended ▶")

    @app_commands.command(name="freeze", description=FREEZE_INFO.overview)
    @app_commands.describe(user="The user to freeze")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def freeze_cmd(self, interaction: discord.Interaction, user: discord.User):
        await require_admin(interaction)
        if await is_protected_target(user, interaction.guild):
            await Messages.respond_error(interaction, "You can't freeze an admin.")
            return
        await User.filter(id=user.id).update(frozen=True)
        await Messages.respond_success(interaction, f"{user.name} has been frozen \U0001F9CA")

    @app_commands.command(name="defrost", description=DEFROST_INFO.overview)
    @app_commands.describe(user="The user to unfreeze")
    @app_commands.default_permissions(manage_guild=True)
    async def unfreeze_cmd(self, interaction: discord.Interaction, user: discord.User):
        await require_admin(interaction)
        await User.filter(id=user.id).update(frozen=False)
        await Messages.respond_success(interaction, f"{user.name} has been defrosted \U0001F525")

    @app_commands.command(name="frozen", description=FROZEN_INFO.overview)
    @app_commands.default_permissions(manage_guild=True)
    async def frozen_cmd(self, interaction: discord.Interaction):
        await require_admin(interaction)
        frozen_list = await User.filter(frozen=True).all()
        if len(frozen_list) < 1:
            await Messages.respond_success(interaction, "There aren't any frozen users", header="Frozen Users")
            return
        pages = banned_user_pages([(u.id, u.name) for u in frozen_list], "Frozen Users", "defrost")
        await Paginator.send_as_response(interaction, pages, ephemeral=True)

    @app_commands.command(name="tipban", description=TIPBAN_INFO.overview)
    @app_commands.describe(user="The user to tip ban")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def tipban_cmd(self, interaction: discord.Interaction, user: discord.User):
        await require_admin(interaction)
        if await is_protected_target(user, interaction.guild):
            await Messages.respond_error(interaction, "You can't tip ban an admin.")
            return
        await User.filter(id=user.id).update(tip_banned=True)
        await Messages.respond_success(interaction, f"{user.name} has been banned \U0001F528")

    @app_commands.command(name="tipunban", description=TIPUNBAN_INFO.overview)
    @app_commands.describe(user="The user to tip unban")
    @app_commands.default_permissions(manage_guild=True)
    async def tipunban_cmd(self, interaction: discord.Interaction, user: discord.User):
        await require_admin(interaction)
        await User.filter(id=user.id).update(tip_banned=False)
        await Messages.respond_success(interaction, f"{user.name} has been unbanned \U0001F5FD")

    @app_commands.command(name="tipbanned", description=TIPBANNED_INFO.overview)
    @app_commands.default_permissions(manage_guild=True)
    async def tipbanned_cmd(self, interaction: discord.Interaction):
        await require_admin(interaction)
        banned_list = await User.filter(tip_banned=True).all()
        if len(banned_list) < 1:
            await Messages.respond_success(interaction, "There aren't any banned users", header="Tip Banned Users")
            return
        pages = banned_user_pages([(u.id, u.name) for u in banned_list], "Tip Banned Users", "tipunban")
        await Paginator.send_as_response(interaction, pages, ephemeral=True)

    @app_commands.command(name="statsban", description=STATSBAN_INFO.overview)
    @app_commands.describe(user="The user to stats ban")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def statsban_cmd(self, interaction: discord.Interaction, user: discord.User):
        await require_admin(interaction)
        if await is_protected_target(user, interaction.guild):
            await Messages.respond_error(interaction, "You can't stats ban an admin.")
            return
        target = await User.filter(id=user.id).first()
        if target is None:
            await Messages.respond_error(interaction, "That user doesn't have an account with me.")
            return
        # Make sure the stats object exists before banning
        async with in_transaction() as conn:
            stats = await target.get_stats(interaction.guild_id)
            stats.banned = True
            await stats.save(update_fields=['banned'], using_db=conn)
        await Messages.respond_success(interaction, f"{user.name} has been stats banned \U0001F528")

    @app_commands.command(name="statsunban", description=STATSUNBAN_INFO.overview)
    @app_commands.describe(user="The user to stats unban")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def statsunban_cmd(self, interaction: discord.Interaction, user: discord.User):
        await require_admin(interaction)
        await Stats.filter(user_id=user.id, server_id=interaction.guild_id, banned=True).update(banned=False)
        await Messages.respond_success(interaction, f"{user.name} has been stats unbanned \U0001F5FD")

    @app_commands.command(name="statsbanned", description=STATSBANNED_INFO.overview)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def statsbanned_cmd(self, interaction: discord.Interaction):
        await require_admin(interaction)
        banned_list = await Stats.filter(banned=True, server_id=interaction.guild_id).prefetch_related('user').all()
        if len(banned_list) < 1:
            await Messages.respond_success(interaction, "There aren't any stats banned users", header="Stats Banned Users")
            return
        pages = banned_user_pages([(s.user.id, s.user.name) for s in banned_list], "Stats Banned Users", "statsunban")
        await Paginator.send_as_response(interaction, pages, ephemeral=True)

    async def adjust_tip_stats(self, interaction: discord.Interaction, user: discord.User, amount: float):
        inv = await require_admin(interaction)
        if not inv.god and await is_protected_target(user, interaction.guild):
            await Messages.respond_error(interaction, "You can't adjust stats of an admin.")
            return
        stats = await Stats.filter(user_id=user.id, server_id=interaction.guild_id).first()
        if stats is None:
            await Messages.respond_error(interaction, "That user doesn't have any stats in this server.")
            return
        async with in_transaction() as conn:
            stats.total_tipped_amount = float(stats.total_tipped_amount) + amount
            stats.legacy_total_tipped_amount = float(stats.legacy_total_tipped_amount) + amount
            await stats.save(using_db=conn, update_fields=['total_tipped_amount', 'legacy_total_tipped_amount'])
        direction = "Increased" if amount >= 0 else "Decreased"
        await Messages.respond_success(interaction, f"{direction} stats of {user.name} by {abs(amount)} {Env.currency_name()}")

    @app_commands.command(name="decreasetips", description=DECREASETIPS_INFO.overview)
    @app_commands.describe(user="The user whose stats to decrease", amount="Amount to subtract from their tip total")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def decreasetips_cmd(self, interaction: discord.Interaction, user: discord.User, amount: float):
        await self.adjust_tip_stats(interaction, user, -amount)

    @app_commands.command(name="increasetips", description=INCREASETIPS_INFO.overview)
    @app_commands.describe(user="The user whose stats to increase", amount="Amount to add to their tip total")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def increasetips_cmd(self, interaction: discord.Interaction, user: discord.User, amount: float):
        await self.adjust_tip_stats(interaction, user, amount)
