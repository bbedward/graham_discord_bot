from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from tortoise.functions import Sum
from util.env import Env
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages
from db.models.user import User
from db.models.stats import Stats
from db.redis import RedisDB

import config
import discord
import datetime
from util.number import NumberUtil

## Command documentation
TIPSTATS_INFO = CommandInfo(
    triggers = ["tipstats"],
    overview = "Display your personal tipping stats for a specific server.",
    details = f"This will display your personal tipping statistics from the server you send the command from. This command can't be used in DM"
)
TOPTIPS_INFO = CommandInfo(
    triggers = ["toptips"],
    overview = "Display biggest tips for a specific server.",
    details = f"This will display the biggest tip of all time, of the current month, and of the day for the current server. This command can't be used in DM"
)
LEADERBOARD_INFO = CommandInfo(
    triggers = ["ballers", "leaderboard"],
    overview = "Show a list of the top 15 tippers this year.",
    details = f"This will display a list of the top 15 tippers on the current server. This command can't be used in DM\n" +
                f"These stats are reset once a year - for all time stats use `{config.Config.instance().command_prefix}legacyboard`"
)
LEGACYBOARD_INFO = CommandInfo(
    triggers = ["legacyboard", "oldballs"],
    overview = "Show a list of the top 15 tippers all time.",
    details = f"This will display a list of the top 15 tippers of all time on the current server. This command can't be used in DM"
)

class StatsCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx: Context):
        ctx.error = False
        # Only allow tip commands in public channels
        msg = ctx.message
        if ChannelUtil.is_private(msg.channel):
            await Messages.send_error_dm(msg.author, "You can only view statistics in a server, not via DM.")
            ctx.error = True
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

        # Can't spam stats commands
        if msg.channel.id in config.Config.instance().get_no_spam_channels():
            ctx.error = True
            await Messages.send_error_dm(msg.author, "I can't post stats in that channel.")
            return

        if ctx.command.name in ['tipstats_cmd']:
            # Make sure user exists in DB
            user = await User.get_user(msg.author)
            if user is None:
                ctx.error = True
                await Messages.send_error_dm(msg.author, f"You should create an account with me first, send me `{config.Config.instance().command_prefix}help` to get started.")
                return
            # Update name, if applicable
            await user.update_name(msg.author.name)
            ctx.user = user

    @commands.command(aliases=TIPSTATS_INFO.triggers)
    async def tipstats_cmd(self, ctx: Context):
        if ctx.error:
            await Messages.add_x_reaction(ctx.message)
            return

        msg = ctx.message
        user: User = ctx.user

        if not ctx.god and await RedisDB.instance().exists(f"tipstatsspam{msg.author.id}{msg.guild.id}"):
            await Messages.add_timer_reaction(msg)
            await Messages.send_error_dm(msg.author, "Why don't you wait awhile before trying to get your tipstats again")
            return

        stats: Stats = await user.get_stats(server_id=msg.guild.id)
        if stats.banned:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "You are stats banned, contact an admin if you want to be unbanned")
            return
        response = ""
        if stats is None or stats.total_tips == 0:
            response = f"<@{msg.author.id}> You haven't sent any tips in this server yet, tip some people and then check your stats later"
        else:
            response = f"<@{msg.author.id}> You have sent **{stats.total_tips}** tips totaling **{NumberUtil.format_float(stats.total_tipped_amount+stats.legacy_total_tipped_amount)} {Env.currency_symbol()}**. Your biggest tip of all time is **{NumberUtil.format_float(stats.top_tip)} {Env.currency_symbol()}**"

        await msg.channel.send(response)
        await RedisDB.instance().set(f"tipstatsspam{msg.author.id}{msg.guild.id}", "as", expires=300)

    @commands.command(aliases=TOPTIPS_INFO.triggers)
    async def toptips_cmd(self, ctx: Context):
        if ctx.error:
            await Messages.add_x_reaction(ctx.message)
            return

        msg = ctx.message   
        if not ctx.god and await RedisDB.instance().exists(f"toptipsspam{msg.channel.id}"):
            await Messages.add_timer_reaction(msg)
            return

        # This would be better to be 1 query but, i'm not proficient enough with tortoise-orm
        top_tip = await Stats.filter(
            server_id=msg.guild.id,
            banned=False
        ).order_by('-top_tip').prefetch_related('user').limit(1).first()
        if top_tip is None:
            await RedisDB.instance().set(f"toptipsspam{msg.channel.id}", "as", expires=300)
            await msg.channel.send("There are no stats for this server yet. Send some tips first!")
            return
        # Get datetime object representing first day of this month
        now = datetime.datetime.utcnow()
        month = str(now.month).zfill(2)
        year = now.year
        first_day_of_month = datetime.datetime.strptime(f'{month}/01/{year} 00:00:00', '%m/%d/%Y %H:%M:%S')
        # Find top tip of the month
        top_tip_month = await Stats.filter(
            server_id=msg.guild.id,
            top_tip_month_at__gte=first_day_of_month,
            banned=False
        ).order_by('-top_tip_month').prefetch_related('user').limit(1).first()
        # Get datetime object representing 24 hours ago
        past_24h = now - datetime.timedelta(hours=24)
        # Find top tip of the month
        top_tip_day = await Stats.filter(
            server_id=msg.guild.id,
            top_tip_day_at__gte=past_24h,
            banned=False
        ).order_by('-top_tip_day').prefetch_related('user').limit(1).first()

        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name='Biggest Tips', icon_url="https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/nano_logo.png")
        new_line = '\n' # Can't use this directly inside f-expression, so store it in a variable
        if top_tip_day is not None:
            embed.description = f"**Last 24 Hours**\n```{NumberUtil.format_float(top_tip_day.top_tip_day)} {Env.currency_symbol()} - by {top_tip_day.user.name}```"
        if top_tip_month is not None:
            embed.description += f"{new_line if top_tip_day is not None else ''}**In {now.strftime('%B')}**\n```{NumberUtil.format_float(top_tip_month.top_tip_month)} {Env.currency_symbol()} - by {top_tip_month.user.name}```"
        embed.description += f"{new_line if top_tip_day is not None or top_tip_month is not None else ''}**All Time**\n```{NumberUtil.format_float(top_tip.top_tip)} {Env.currency_symbol()} - by {top_tip.user.name}```"

        # No spam
        await RedisDB.instance().set(f"toptipsspam{msg.channel.id}", "as", expires=300)

        await msg.channel.send(embed=embed)

    @commands.command(aliases=LEADERBOARD_INFO.triggers)
    async def leaderboard_cmd(self, ctx: Context):
        if ctx.error:
            await Messages.add_x_reaction(ctx.message)
            return

        msg = ctx.message

        if not ctx.god and await RedisDB.instance().exists(f"ballerspam{msg.channel.id}"):
            await Messages.add_timer_reaction(msg)
            await Messages.send_error_dm(msg.author, "Why don't you wait awhile before checking the ballers list again")
            return

        # Get list
        ballers = await Stats.filter(server_id=msg.guild.id, banned=False).order_by('-total_tipped_amount').prefetch_related('user').limit(15).all()

        if len(ballers) == 0:
            await msg.channel.send(f"<@{msg.author.id}> There are no stats for this server yet, send some tips!")
            return

        response_msg = "```"
        # Get biggest tip to adjust the padding
        biggest_num = 0
        for stats in ballers:
            length = len(f"{NumberUtil.format_float(stats.total_tipped_amount)} {Env.currency_symbol()}")
            if length > biggest_num:
                biggest_num = length
        for rank, stats in enumerate(ballers, start=1):
            adj_rank = str(rank) if rank >= 10 else f" {rank}"
            user_name = stats.user.name
            amount_str = f"{NumberUtil.format_float(stats.total_tipped_amount)} {Env.currency_symbol()}"
            response_msg += f"{adj_rank}. {amount_str.ljust(biggest_num)} - by {user_name}\n" 
        response_msg += "```"

        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name=f"Here are the top {len(ballers)} tippers \U0001F44F", icon_url="https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/nano_logo.png")
        embed.description = response_msg
        embed.set_footer(text=f"Use {config.Config.instance().command_prefix} legacyboard for all-time stats")

        await RedisDB.instance().set(f"ballerspam{msg.channel.id}", "as", expires=300)
        await msg.channel.send(f"<@{msg.author.id}>", embed=embed)

    @commands.command(aliases=LEGACYBOARD_INFO.triggers)
    async def legacyboard_cmd(self, ctx: Context):
        if ctx.error:
            await Messages.add_x_reaction(ctx.message)
            return

        msg = ctx.message

        if not ctx.god and await RedisDB.instance().exists(f"ballerspam{msg.channel.id}"):
            await Messages.add_timer_reaction(msg)
            await Messages.send_error_dm(msg.author, "Why don't you wait awhile before checking the ballers list again")
            return

        # Get list
        # TODO - can't sum multiple columns
        # https://github.com/tortoise/tortoise-orm/issues/257
        #ballers = await Stats.filter(server_id=msg.guild.id, banned=False).annotate(tip_sum=Sum('total_tipped_amount' + 'legacy_total_tipped_amount')) .order_by('-tip_sum').prefetch_related('user').limit(15).all()
        ballers = await Stats.filter(server_id=msg.guild.id, banned=False).order_by('-legacy_total_tipped_amount').prefetch_related('user').limit(15).all()

        if len(ballers) == 0:
            await msg.channel.send(f"<@{msg.author.id}> There are no stats for this server yet, send some tips!")
            return

        response_msg = "```"
        # Get biggest tip to adjust the padding
        biggest_num = 0
        for stats in ballers:
            # TODO change to stats.tip_sum
            length = len(f"{NumberUtil.format_float(stats.legacy_total_tipped_amount)} {Env.currency_symbol()}")
            if length > biggest_num:
                biggest_num = length
        for rank, stats in enumerate(ballers, start=1):
            adj_rank = str(rank) if rank >= 10 else f" {rank}"
            user_name = stats.user.name
            amount_str = f"{NumberUtil.format_float(stats.legacy_total_tipped_amount)} {Env.currency_symbol()}"
            response_msg += f"{adj_rank}. {amount_str.ljust(biggest_num)} - by {user_name}\n" 
        response_msg += "```"

        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name=f"Here are the top {len(ballers)} tippers of all time\U0001F44F", icon_url="https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/nano_logo.png")
        embed.description = response_msg

        await RedisDB.instance().set(f"ballerspam{msg.channel.id}", "as", expires=300)
        await msg.channel.send(f"<@{msg.author.id}>", embed=embed)