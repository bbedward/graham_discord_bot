import discord
from discord import app_commands
from discord.ext import commands

from db.models.muted import Muted
from db.models.user import User
from models.command import CommandInfo
from util.discord.messages import Messages
from util.discord.paginator import Entry, Page, Paginator
from util.discord.resolver import require_user

## Command documentation
MUTE_INFO = CommandInfo(
    triggers = ["mute"],
    overview = "Mute a user",
    details = "No longer receive tip notifications from a specific user. Example: `/mute @someone`"
)
UNMUTE_INFO = CommandInfo(
    triggers = ["unmute"],
    overview = "Unmute a user",
    details = "Receive tip notifications from a user again. Example: `/unmute @someone`"
)
MUTED_INFO = CommandInfo(
    triggers = ["muted"],
    overview = "View list of muted users",
    details = "View the list of every user you have muted."
)

class UserOptionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="mute", description=MUTE_INFO.overview)
    @app_commands.describe(user="The user to stop receiving tip notifications from")
    async def mute_cmd(self, interaction: discord.Interaction, user: discord.User):
        inv = await require_user(interaction)
        if user.id == interaction.user.id:
            await Messages.respond_error(interaction, "You can't mute yourself.")
            return
        target_user = await User.get_user(user)
        if target_user is None:
            await Messages.respond_error(interaction, "That user doesn't have an account with me.")
            return
        await Muted.mute_user(inv.user, target_user)
        await Messages.respond_success(interaction, f"Successfully muted {user.name}")

    @app_commands.command(name="unmute", description=UNMUTE_INFO.overview)
    @app_commands.describe(user="The user to receive tip notifications from again")
    async def unmute_cmd(self, interaction: discord.Interaction, user: discord.User):
        inv = await require_user(interaction)
        target_user = await User.get_user(user)
        if target_user is None:
            await Messages.respond_error(interaction, "That user doesn't have an account with me.")
            return
        await Muted.unmute_user(inv.user, target_user)
        await Messages.respond_success(interaction, f"Successfully unmuted {user.name}")

    @app_commands.command(name="muted", description=MUTED_INFO.overview)
    async def muted_cmd(self, interaction: discord.Interaction):
        inv = await require_user(interaction)
        muted_list = await Muted.filter(user=inv.user).prefetch_related('target_user').all()
        if len(muted_list) < 1:
            await Messages.respond_success(interaction, "You haven't muted anybody.", header="Muted Users")
            return

        entries = [Entry(f"{u.target_user.name}", f"Unmute with `/unmute` and their ID: {u.target_user.id}") for u in muted_list]
        author = "Muted Users"
        description = "Use `/unmute` to unmute a user"
        pages = [Page(entries=entries[i:i + 15], author=author, description=description) for i in range(0, len(entries), 15)]
        await Paginator.send_as_response(interaction, pages, ephemeral=True)
