from discord.ext import commands
from discord.ext.commands import Bot, Context
from db.models.user import User
from db.redis import RedisDB
from models.command import CommandInfo

import config
import logging
from util.discord.messages import Messages
from util.discord.paginator import Entry, Page, Paginator

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
    details = "Completely freeze all mentioned users or user ID accounts"
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

class Admin(commands.Cog):
    """Commands for admins only"""
    def __init__(self, bot: Bot):
        self.bot = bot
        self.logger = logging.getLogger()

    async def cog_before_invoke(self, ctx: Context):
        ctx.error = False
        # Only allow tip commands in public channels
        msg = ctx.message
        # Restrict all commands to admins only
        ctx.god = msg.author.id in config.Config.instance().get_admin_ids()
        if not ctx.god:
            ctx.admin = False
            author: discord.Member = msg.author
            for role in author.roles:
                if role.id in config.Config.instance().get_admin_roles():
                    ctx.admin = True
                    break
        else:
            ctx.admin = True

        if not ctx.admin:
            ctx.error = True

    @commands.command(aliases=PAUSE_INFO.triggers)
    async def pause_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        await RedisDB.instance().pause()
        await msg.add_reaction('\u23F8') # Pause
        await msg.author.send("Transaction activity is now suspended")

    @commands.command(aliases=RESUME_INFO.triggers)
    async def resume_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        await RedisDB.instance().resume()
        await msg.add_reaction('\u25B6') # Pause
        await msg.author.send("Transaction activity is no longer suspended")

    @commands.command(aliases=FREEZE_INFO.triggers)
    async def freeze_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        freeze_ids = []
        # Get mentioned users
        for m in msg.mentions:
            freeze_ids.append(m.id)
    
        # Get users they are freezing by ID alone
        for sec in msg.content.split():
            try:
                numeric = int(sec.strip())
                user = await self.bot.fetch_user(numeric)
                if user is not None:
                    freeze_ids.append(user.id)
            except Exception:
                pass

        # remove duplicates and admins
        freeze_ids = set(freeze_ids)
        freeze_ids = [x for x in freeze_ids if x not in config.Config.instance().get_admin_ids()]
        for f in freeze_ids:
            memba = msg.guild.get_member(f)
            if memba is not None:
                for r in memba.roles:
                    if r.id in [config.Config.instance().get_admin_roles()]:
                        freeze_ids.remove(r.id)

        if len(freeze_ids) < 1:
            await Messages.add_x_reaction(msg)
            await msg.author.send("Your message has no users to freeze")
            return

        await User.filter(id__in=freeze_ids).update(frozen=True)

        await msg.author.send(f"{len(freeze_ids)} users have been frozen")
        await msg.add_reaction("\U0001F9CA")

    @commands.command(aliases=DEFROST_INFO.triggers)
    async def unfreeze_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        freeze_ids = []
        # Get mentioned users
        for m in msg.mentions:
            freeze_ids.append(m.id)

        # Get users they are freezing by ID alone
        for sec in msg.content.split():
            try:
                numeric = int(sec.strip())
                user = await self.bot.fetch_user(numeric)
                if user is not None:
                    freeze_ids.append(user.id)
            except Exception:
                pass

        # remove duplicates and admins
        freeze_ids = set(freeze_ids)
        freeze_ids = [x for x in freeze_ids if x not in config.Config.instance().get_admin_ids()]
        for f in freeze_ids:
            memba = msg.guild.get_member(f)
            if memba is not None:
                for r in memba.roles:
                    if r.id in [config.Config.instance().get_admin_roles()]:
                        freeze_ids.remove(r.id)

        if len(freeze_ids) < 1:
            await Messages.add_x_reaction(msg)
            await msg.author.send("Your message has no users to defrost")
            return

        # TODO - tortoise doesnt give us any feedback on update counts atm
        # https://github.com/tortoise/tortoise-orm/issues/126
        await User.filter(id__in=freeze_ids).update(frozen=False)

        await msg.author.send(f"{len(freeze_ids)} users have been defrosted")
        await msg.add_reaction("\U0001F525")

    @commands.command(aliases=FROZEN_INFO.triggers)
    async def frozen_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        frozen_list = await User.filter(frozen=True).all()

        if len(frozen_list) < 1:
            await msg.author.send("There aren't any frozen users")
            return

        # Build user list
        entries = []
        for u in frozen_list:
            entries.append(Entry(f"{u.id}:{u.name}", f"Unfreeze with `{config.Config.instance().command_prefix}defrost {u.id}`"))

        # Build pages
        pages = []
        # Overview
        author=f"Frozen Users"
        description = f"Use `{config.Config.instance().command_prefix}defrost <user_id>` to unfreeze a user"
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
