from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo

import config
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages
from db.models.muted import Muted
from db.models.user import User
from util.discord.paginator import Entry, Page, Paginator

## Command documentation
MUTE_INFO = CommandInfo(
    triggers = ["mute"],
    overview = "Mute a user by ID",
    details = f"No longer receive tip notifications from a specific user. Example: `{config.Config.instance().command_prefix}mute 419483863115366410`"
)
UNMUTE_INFO = CommandInfo(
    triggers = ["unmute"],
    overview = "Unmute a user by ID",
    details = f"Receive tip notifications from a user again. Example: `{config.Config.instance().command_prefix}unmute 419483863115366410`"
)
MUTED_INFO = CommandInfo(
    triggers = ["muted"],
    overview = "View list of muted users",
    details = f"View the list of every user you have muted."
)


class UserOptionsCog(commands.Cog):
    """Commands for admins only"""
    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx: Context):
        ctx.error = False
        # Only allow mute commands in private channels
        msg = ctx.message
        if not ChannelUtil.is_private(msg.channel):
            ctx.error = True
            await Messages.send_error_dm(msg.author, "You can only do this in DM")
            return
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
        ctx.user = user

    @commands.command(aliases=MUTE_INFO.triggers)
    async def mute_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user

        to_mute = []
        for u in ctx.message.content.split():
            try:
                u_id = int(u.strip())
                if u_id == msg.author.id:
                    continue
                discord_user = self.bot.get_user(u_id)
                if discord_user is not None:
                    to_mute.append(discord_user)
            except Exception:
                pass

        if len(to_mute) < 1:
            await Messages.send_usage_dm(msg.author, MUTE_INFO)
            return

        # Mute users
        muted_count = 0
        for u in to_mute:
            try:
                target_user = await User.get_user(u)
                if target_user is not None:
                    await Muted.mute_user(user, target_user)
                    muted_count += 1
            except Exception:
                pass

        if muted_count < 1:
            await Messages.send_error_dm(msg.author, "I was unable to mute any users you mentioned.")
            return

        await Messages.send_success_dm(msg.author, f"Successfully muted {muted_count} user(s)")

    @commands.command(aliases=UNMUTE_INFO.triggers)
    async def unmute_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user

        to_unmute = []
        for u in ctx.message.content.split():
            try:
                u_id = int(u.strip())
                if u_id == msg.author.id:
                    continue
                discord_user = self.bot.get_user(u_id)
                if discord_user is not None:
                    to_unmute.append(discord_user)
            except Exception:
                pass

        if len(to_unmute) < 1:
            await Messages.send_usage_dm(msg.author, UNMUTE_INFO)
            return

        # Ununmute users
        unmuted_count = 0
        for u in to_unmute:
            try:
                target_user = await User.get_user(u)
                if target_user is not None:
                    await Muted.unmute_user(user, target_user)
                    unmuted_count += 1
            except Exception:
                pass

        if unmuted_count < 1:
            await Messages.send_error_dm(msg.author, "I was unable to unmute any users you mentioned.")
            return

        await Messages.send_success_dm(msg.author, f"Successfully unmuted {unmuted_count} user(s)")

    @commands.command(aliases=MUTED_INFO.triggers)
    async def muted_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user

        if not ChannelUtil.is_private(msg.channel):
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "You can only view users you have muted in DM")
            return

        muted_list = await Muted.filter(user=ctx.user).prefetch_related('target_user').all()

        if len(muted_list) < 1:
            await msg.author.send("You haven't muted anybody.")
            return

        # Build user list
        entries = []
        for u in muted_list:
            entries.append(Entry(f"{u.target_user.name}", f"Unmute with `{config.Config.instance().command_prefix}unmute {u.target_user.id}`"))

        # Build pages
        pages = []
        # Overview
        author=f"Muted Users"
        description = f"Use `{config.Config.instance().command_prefix}unmute <user_id>` to unmute a user"
        i = 0
        entry_subset = []
        for e in entries:
            entry_subset.append(e)
            if i == 14:
                pages.append(Page(entries=entry_subset, author=author, description=description))
                i = 0
                entry_subset = []
            else:
                i += 1
        if len(entry_subset) > 0:
            pages.append(Page(entries=entry_subset, author=author, description=description))

        # Start pagination
        pages = Paginator(self.bot, message=msg, page_list=pages,as_dm=True)
        await pages.paginate(start_page=1)