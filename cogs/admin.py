from discord.ext import commands
from discord.ext.commands import Bot, Context
from db.models.stats import Stats
from db.models.user import User
from db.redis import RedisDB
from models.command import CommandInfo
from tortoise.transactions import in_transaction

import config
import logging
from util.discord.messages import Messages
from util.discord.paginator import Entry, Page, Paginator
from util.discord.channel import ChannelUtil
from util.env import Env
from util.regex import RegexUtil, AmountMissingException

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
    details = f"`{config.Config.instance().command_prefix}decreasetips 1000 @bbedward` - Reduce users tip count by 1000 {Env.currency_name()}"
)
INCREASETIPS_INFO = CommandInfo(
    triggers = ["increasetips"],
    overview = "Increase tip stat total",
    details = f"`{config.Config.instance().command_prefix}increasetips 1000 @bbedward` - Increase users tip count by 1000 {Env.currency_name()}"
)

class AdminCog(commands.Cog):
    """Commands for admins only"""
    def __init__(self, bot: Bot):
        self.bot = bot
        self.logger = logging.getLogger()

    async def cog_before_invoke(self, ctx: Context):
        ctx.error = False
        msg = ctx.message
        # Restrict all commands to admins only
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

        if ChannelUtil.is_private(msg.channel):
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "You can't freeze via DM, need to do it in a server channel")
            return

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

    @commands.command(aliases=TIPBAN_INFO.triggers)
    async def tipban_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        if ChannelUtil.is_private(msg.channel):
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "You can't ban via DM, need to do it in a server channel")
            return

        ban_ids = []
        # Get mentioned users
        for m in msg.mentions:
            ban_ids.append(m.id)
    
        # Get users they are banning by ID alone
        for sec in msg.content.split():
            try:
                numeric = int(sec.strip())
                user = await self.bot.fetch_user(numeric)
                if user is not None:
                    ban_ids.append(user.id)
            except Exception:
                pass

        # remove duplicates and admins
        ban_ids = set(ban_ids)
        ban_ids = [x for x in ban_ids if x not in config.Config.instance().get_admin_ids()]
        for f in ban_ids:
            memba = msg.guild.get_member(f)
            if memba is not None:
                for r in memba.roles:
                    if r.id in [config.Config.instance().get_admin_roles()]:
                        ban_ids.remove(r.id)

        if len(ban_ids) < 1:
            await Messages.add_x_reaction(msg)
            await msg.author.send("Your message has no users to ban")
            return

        await User.filter(id__in=ban_ids).update(tip_banned=True)

        await msg.author.send(f"{len(ban_ids)} users have been banned")
        await msg.add_reaction("\U0001F528")

    @commands.command(aliases=TIPUNBAN_INFO.triggers)
    async def tipunban_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        ban_ids = []
        # Get mentioned users
        for m in msg.mentions:
            ban_ids.append(m.id)
    
        # Get users they are banning by ID alone
        for sec in msg.content.split():
            try:
                numeric = int(sec.strip())
                user = await self.bot.fetch_user(numeric)
                if user is not None:
                    ban_ids.append(user.id)
            except Exception:
                pass

        # remove duplicates and admins
        ban_ids = set(ban_ids)

        if len(ban_ids) < 1:
            await Messages.add_x_reaction(msg)
            await msg.author.send("Your message has no users to unban")
            return

        # TODO - tortoise doesnt give us any feedback on update counts atm
        # https://github.com/tortoise/tortoise-orm/issues/126
        await User.filter(id__in=ban_ids).update(tip_banned=False)

        await msg.author.send(f"{len(ban_ids)} users have been unbanned")
        await msg.add_reaction("\U0001F5FD")

    @commands.command(aliases=TIPBANNED_INFO.triggers)
    async def tipbanned_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        banned_list = await User.filter(tip_banned=True).all()

        if len(banned_list) < 1:
            await msg.author.send("There aren't any banned users")
            return

        # Build user list
        entries = []
        for u in banned_list:
            entries.append(Entry(f"{u.id}:{u.name}", f"Unban with `{config.Config.instance().command_prefix}tipunban {u.id}`"))

        # Build pages
        pages = []
        # Overview
        author=f"Tip Banned Users"
        description = f"Use `{config.Config.instance().command_prefix}tipunban <user_id>` to unban a user"
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

    @commands.command(aliases=STATSBAN_INFO.triggers)
    async def statsban_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        if ChannelUtil.is_private(msg.channel):
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "You can only stats ban in a public channel")
            return

        ban_ids = []
        # Get mentioned users
        for m in msg.mentions:
            ban_ids.append(m.id)
    
        # Get users they are banning by ID alone
        for sec in msg.content.split():
            try:
                numeric = int(sec.strip())
                user = await self.bot.fetch_user(numeric)
                if user is not None:
                    ban_ids.append(user.id)
            except Exception:
                pass

        # remove duplicates and admins
        ban_ids = set(ban_ids)
        ban_ids = [x for x in ban_ids if x not in config.Config.instance().get_admin_ids()]
        for f in ban_ids:
            memba = msg.guild.get_member(f)
            if memba is not None:
                for r in memba.roles:
                    if r.id in [config.Config.instance().get_admin_roles()]:
                        ban_ids.remove(r.id)

        if len(ban_ids) < 1:
            await Messages.add_x_reaction(msg)
            await msg.author.send("Your message has no users to ban")
            return

        # We need to make sure that the stats objects are created for these users before banning them
        to_ban = await User.filter(id__in=ban_ids).all()
        async with in_transaction() as conn:
            for u in to_ban:
                stats = await u.get_stats(msg.guild.id)
                stats.banned = True
                await stats.save(update_fields=['banned'], using_db=conn)

        await msg.author.send(f"{len(ban_ids)} users have been banned")
        await msg.add_reaction("\U0001F528")

    @commands.command(aliases=STATSUNBAN_INFO.triggers)
    async def statsunban_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        if ChannelUtil.is_private(msg.channel):
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "You can only stats unban in a public channel")
            return

        ban_ids = []
        # Get mentioned users
        for m in msg.mentions:
            ban_ids.append(m.id)
    
        # Get users they are banning by ID alone
        for sec in msg.content.split():
            try:
                numeric = int(sec.strip())
                user = await self.bot.fetch_user(numeric)
                if user is not None:
                    ban_ids.append(user.id)
            except Exception:
                pass

        # remove duplicates and admins
        ban_ids = set(ban_ids)

        if len(ban_ids) < 1:
            await Messages.add_x_reaction(msg)
            await msg.author.send("Your message has no users to unban")
            return

        # TODO - tortoise doesnt give us any feedback on update counts atm
        # https://github.com/tortoise/tortoise-orm/issues/126
        await Stats.filter(user_id__in=ban_ids, server_id=msg.guild.id, banned=True).update(banned=False)

        await msg.author.send(f"{len(ban_ids)} users have been unbanned")
        await msg.add_reaction("\U0001F5FD")

    @commands.command(aliases=STATSBANNED_INFO.triggers)
    async def statsbanned_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        if ChannelUtil.is_private(msg.channel):
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "You can only view stats banned in a public channel")
            return

        banned_list = await Stats.filter(banned=True, server_id=msg.guild.id).prefetch_related('user').all()

        if len(banned_list) < 1:
            await msg.author.send("There aren't any banned users")
            return

        # Build user list
        entries = []
        for u in banned_list:
            entries.append(Entry(f"{u.user.id}:{u.user.name}", f"Unban with `{config.Config.instance().command_prefix}statsunban {u.user.id}`"))

        # Build pages
        pages = []
        # Overview
        author=f"Stats Banned Users"
        description = f"Use `{config.Config.instance().command_prefix}statsunban <user_id>` to unban a user"
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

    @commands.command(aliases=DECREASETIPS_INFO.triggers)
    async def decreasetips_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        decreasetip_ids = []
        # Get mentioned users
        for m in msg.mentions:
            decreasetip_ids.append(m.id)

        # remove duplicates and avoid admins
        decreasetip_ids = set(decreasetip_ids)
        decreasetip_ids = [x for x in decreasetip_ids if x not in config.Config.instance().get_admin_ids()]
        if msg.author.id not in config.Config.instance().get_admin_ids():
            for d in decreasetip_ids:
                memba = msg.guild.get_member(d)
                if memba is not None:
                    for r in memba.roles:
                        if r.id in [config.Config.instance().get_admin_roles()]:
                            d.remove(r.id)


        if len(decreasetip_ids) < 1:
            await Messages.add_x_reaction(msg)
            await msg.author.send("Your message has no users to decreasetips for")
            return

        try:
            amount = RegexUtil.find_float(msg.content)
        except AmountMissingException:
            await Messages.send_usage_dm(msg.author, DECREASETIPS_INFO)
            return

        # TODO - tortoise doesnt give us any feedback on update counts atm
        # https://github.com/tortoise/tortoise-orm/issues/126
        # TODO - we also don't have atomic updates :/
        decrease_tip_count = 0
        for u in await Stats.filter(user_id__in=decreasetip_ids, server_id=msg.guild.id).all():
            async with in_transaction() as conn:
                u.total_tipped_amount = float(u.total_tipped_amount) - amount
                u.legacy_total_tipped_amount = float(u.legacy_total_tipped_amount) - amount
                await u.save(using_db=conn, update_fields=['total_tipped_amount', 'legacy_total_tipped_amount'])
                decrease_tip_count += 1

        await msg.author.send(f"Decreased stats of {decrease_tip_count} by {amount} {Env.currency_name()}")
        await msg.add_reaction("\u2796")

    @commands.command(aliases=INCREASETIPS_INFO.triggers)
    async def increasetips_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message

        increasetip_ids = []
        # Get mentioned users
        for m in msg.mentions:
            increasetip_ids.append(m.id)

        # remove duplicates and avoid admins
        increasetip_ids = set(increasetip_ids)
        increasetip_ids = [x for x in increasetip_ids if x not in config.Config.instance().get_admin_ids()]
        if msg.author.id not in config.Config.instance().get_admin_ids():
            for d in increasetip_ids:
                memba = msg.guild.get_member(d)
                if memba is not None:
                    for r in memba.roles:
                        if r.id in [config.Config.instance().get_admin_roles()]:
                            d.remove(r.id)


        if len(increasetip_ids) < 1:
            await Messages.add_x_reaction(msg)
            await msg.author.send("Your message has no users to increasetips for")
            return

        try:
            amount = RegexUtil.find_float(msg.content)
        except AmountMissingException:
            await Messages.send_usage_dm(msg.author, INCREASETIPS_INFO)
            return

        # TODO - tortoise doesnt give us any feedback on update counts atm
        # https://github.com/tortoise/tortoise-orm/issues/126
        # TODO - we also don't have atomic updates :/
        increase_tip_count = 0
        for u in await Stats.filter(user_id__in=increasetip_ids, server_id=msg.guild.id).all():
            async with in_transaction() as conn:
                u.total_tipped_amount = float(u.total_tipped_amount) + amount
                u.legacy_total_tipped_amount = float(u.legacy_total_tipped_amount) + amount
                await u.save(using_db=conn, update_fields=['total_tipped_amount', 'legacy_total_tipped_amount'])
                increase_tip_count += 1

        await msg.author.send(f"Increased stats of {increase_tip_count} by {amount} {Env.currency_name()}")
        await msg.add_reaction("\u2795")