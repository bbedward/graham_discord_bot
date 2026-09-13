import datetime

import discord
from discord import app_commands
from discord.ext import commands

import config
from db.models.stats import Stats
from db.redis import RedisDB
from models.command import CommandInfo
from rpc.client import RPCClient
from util.discord.messages import Messages
from util.discord.resolver import require_user, resolve
from util.env import Env

## Command documentation
TIPSTATS_INFO = CommandInfo(
    triggers = ["tipstats"],
    overview = "Display your personal tipping stats for a specific server.",
    details = "This will display your personal tipping statistics from the server you send the command from. This command can't be used in DM"
)
TOPTIPS_INFO = CommandInfo(
    triggers = ["toptips"],
    overview = "Display biggest tips for a specific server.",
    details = "This will display the biggest tip of all time, of the current month, and of the day for the current server. This command can't be used in DM"
)
LEADERBOARD_INFO = CommandInfo(
    triggers = ["ballers", "leaderboard"],
    overview = "Show a list of the top 15 tippers this year.",
    details = "This will display a list of the top 15 tippers on the current server. This command can't be used in DM\n" +
                "These stats are reset once a year - for all time stats use `/legacyboard`"
)
LEGACYBOARD_INFO = CommandInfo(
    triggers = ["legacyboard", "oldballs"],
    overview = "Show a list of the top 15 tippers all time.",
    details = "This will display a list of the top 15 tippers of all time on the current server. This command can't be used in DM"
)
BLOCKS_INFO = CommandInfo(
    triggers = ["blocks"],
    overview = "Show the node's block count.",
    details = "Displays the current block count and unchecked count from the node."
)

def graham_embed(author_name: str, description: str) -> discord.Embed:
    embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
    embed.set_author(name=author_name, icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
    embed.description = description
    return embed

class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def check_channel(self, interaction: discord.Interaction) -> bool:
        if interaction.channel_id in config.Config.instance().get_no_spam_channels():
            await Messages.respond_error(interaction, "I can't post stats in that channel.")
            return False
        return True

    @app_commands.command(name="tipstats", description=TIPSTATS_INFO.overview)
    @app_commands.guild_only()
    async def tipstats_cmd(self, interaction: discord.Interaction):
        inv = await require_user(interaction)
        if not await self.check_channel(interaction):
            return

        if not inv.god and await RedisDB.instance().exists(f"tipstatsspam{interaction.user.id}{interaction.guild_id}"):
            await Messages.respond_error(interaction, "Why don't you wait awhile before trying to get your tipstats again")
            return

        stats: Stats = await inv.user.get_stats(server_id=interaction.guild_id)
        if stats.banned:
            await Messages.respond_error(interaction, "You are stats banned, contact an admin if you want to be unbanned")
            return
        if stats is None or stats.total_tips == 0:
            response = f"<@{interaction.user.id}> You haven't sent any tips in this server yet, tip some people and then check your stats later"
        else:
            response = f"<@{interaction.user.id}> You have sent **{stats.total_tips}** tips totaling **{Env.format_float(stats.legacy_total_tipped_amount)} {Env.currency_symbol()}**. Your biggest tip of all time is **{Env.format_float(stats.top_tip)} {Env.currency_symbol()}**"

        await interaction.response.send_message(response)
        await RedisDB.instance().set(f"tipstatsspam{interaction.user.id}{interaction.guild_id}", "as", expires=300)

    @app_commands.command(name="toptips", description=TOPTIPS_INFO.overview)
    @app_commands.guild_only()
    async def toptips_cmd(self, interaction: discord.Interaction):
        inv = await resolve(interaction, check_paused=False, require_registered=False)
        if not await self.check_channel(interaction):
            return
        if not inv.god and await RedisDB.instance().exists(f"toptipsspam{interaction.channel_id}"):
            await Messages.respond_error(interaction, "Why don't you wait awhile before checking the top tips again")
            return

        # This would be better to be 1 query but, i'm not proficient enough with tortoise-orm
        top_tip = await Stats.filter(
            server_id=interaction.guild_id,
            banned=False
        ).order_by('-top_tip').prefetch_related('user').limit(1).first()
        if top_tip is None:
            await RedisDB.instance().set(f"toptipsspam{interaction.channel_id}", "as", expires=300)
            await interaction.response.send_message("There are no stats for this server yet. Send some tips first!")
            return
        # Get datetime object representing first day of this month
        now = datetime.datetime.now(datetime.timezone.utc)
        month = str(now.month).zfill(2)
        year = now.year
        first_day_of_month = datetime.datetime.strptime(f'{month}/01/{year} 00:00:00', '%m/%d/%Y %H:%M:%S')
        # Find top tip of the month
        top_tip_month = await Stats.filter(
            server_id=interaction.guild_id,
            top_tip_month_at__gte=first_day_of_month,
            banned=False
        ).order_by('-top_tip_month').prefetch_related('user').limit(1).first()
        # Get datetime object representing 24 hours ago
        past_24h = now - datetime.timedelta(hours=24)
        top_tip_day = await Stats.filter(
            server_id=interaction.guild_id,
            top_tip_day_at__gte=past_24h,
            banned=False
        ).order_by('-top_tip_day').prefetch_related('user').limit(1).first()

        description = ""
        if top_tip_day is not None:
            description = f"**Last 24 Hours**\n```{Env.format_float(top_tip_day.top_tip_day)} {Env.currency_symbol()} - by {top_tip_day.user.name}```"
        if top_tip_month is not None:
            description += f"{chr(10) if top_tip_day is not None else ''}**In {now.strftime('%B')}**\n```{Env.format_float(top_tip_month.top_tip_month)} {Env.currency_symbol()} - by {top_tip_month.user.name}```"
        description += f"{chr(10) if top_tip_day is not None or top_tip_month is not None else ''}**All Time**\n```{Env.format_float(top_tip.top_tip)} {Env.currency_symbol()} - by {top_tip.user.name}```"

        await RedisDB.instance().set(f"toptipsspam{interaction.channel_id}", "as", expires=300)
        await interaction.response.send_message(embed=graham_embed('Biggest Tips', description))

    def format_leaderboard(self, ballers: list, amount_of) -> str:
        response_msg = "```"
        biggest_num = max(len(f"{Env.format_float(amount_of(stats))} {Env.currency_symbol()}") for stats in ballers)
        for rank, stats in enumerate(ballers, start=1):
            adj_rank = str(rank) if rank >= 10 else f" {rank}"
            amount_str = f"{Env.format_float(amount_of(stats))} {Env.currency_symbol()}"
            response_msg += f"{adj_rank}. {amount_str.ljust(biggest_num)} - by {stats.user.name}\n"
        response_msg += "```"
        return response_msg

    @app_commands.command(name="ballers", description=LEADERBOARD_INFO.overview)
    @app_commands.guild_only()
    async def leaderboard_cmd(self, interaction: discord.Interaction):
        inv = await resolve(interaction, check_paused=False, require_registered=False)
        if not await self.check_channel(interaction):
            return
        if not inv.god and await RedisDB.instance().exists(f"ballerspam{interaction.channel_id}"):
            await Messages.respond_error(interaction, "Why don't you wait awhile before checking the ballers list again")
            return

        ballers = await Stats.filter(server_id=interaction.guild_id, banned=False).order_by('-total_tipped_amount').prefetch_related('user').limit(15).all()
        if len(ballers) == 0:
            await interaction.response.send_message(f"<@{interaction.user.id}> There are no stats for this server yet, send some tips!")
            return

        embed = graham_embed(f"Here are the top {len(ballers)} tippers \U0001F44F", self.format_leaderboard(ballers, lambda s: s.total_tipped_amount))
        embed.set_footer(text="Use /legacyboard for all-time stats")

        await RedisDB.instance().set(f"ballerspam{interaction.channel_id}", "as", expires=300)
        await interaction.response.send_message(f"<@{interaction.user.id}>", embed=embed)

    @app_commands.command(name="legacyboard", description=LEGACYBOARD_INFO.overview)
    @app_commands.guild_only()
    async def legacyboard_cmd(self, interaction: discord.Interaction):
        inv = await resolve(interaction, check_paused=False, require_registered=False)
        if not await self.check_channel(interaction):
            return
        if not inv.god and await RedisDB.instance().exists(f"ballerspam{interaction.channel_id}"):
            await Messages.respond_error(interaction, "Why don't you wait awhile before checking the ballers list again")
            return

        ballers = await Stats.filter(server_id=interaction.guild_id, banned=False).order_by('-legacy_total_tipped_amount').prefetch_related('user').limit(15).all()
        if len(ballers) == 0:
            await interaction.response.send_message(f"<@{interaction.user.id}> There are no stats for this server yet, send some tips!")
            return

        embed = graham_embed(f"Here are the top {len(ballers)} tippers of all time\U0001F44F", self.format_leaderboard(ballers, lambda s: s.legacy_total_tipped_amount))

        await RedisDB.instance().set(f"ballerspam{interaction.channel_id}", "as", expires=300)
        await interaction.response.send_message(f"<@{interaction.user.id}>", embed=embed)

    @app_commands.command(name="blocks", description=BLOCKS_INFO.overview)
    async def blocks_cmd(self, interaction: discord.Interaction):
        inv = await resolve(interaction, check_paused=False, require_registered=False)
        spam_key = f"blocksspam{interaction.channel_id if interaction.guild_id is not None else interaction.user.id}"
        if not inv.god and await RedisDB.instance().exists(spam_key):
            await Messages.respond_error(interaction, "Why don't you wait awhile before checking the block count again?")
            return

        count, unchecked = await RPCClient.instance().block_count()
        if count is None or unchecked is None:
            await Messages.respond_error(interaction, "I couldn't retrieve the current block count")
            return

        embed = graham_embed("Here's how many blocks I have", f"```Count: {count:,}\nUnchecked: {unchecked:,}```")
        await RedisDB.instance().set(spam_key, "as", expires=120)
        await interaction.response.send_message(embed=embed, ephemeral=interaction.guild_id is None)
