from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from util.env import Env
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages
from db.models.user import User
from db.models.stats import Stats
from db.redis import RedisDB

import config

## Command documentation
TIPSTATS_INFO = CommandInfo(
    triggers = ["tipstats"],
    overview = "Display your personal tipping stats for a specific server.",
    details = f"This will display your personal tipping statistics from the server you send the command from. This command can't be used in DM"
)

class TipStats(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx: Context):
        ctx.error = False
        # TODO - account for stats banned
        # Only allow tip commands in public channels
        msg = ctx.message
        if ChannelUtil.is_private(msg.channel):
            await Messages.send_error_dm(msg.author, "You can only view statistics in a server, not via DM.")
            ctx.error = True
            return
        # Make sure user exists in DB
        user = await User.get_user(msg.author)
        if user is None:
            ctx.error = True
            await Messages.send_error_dm(msg.author, f"You should create an account with me first, send me `{config.Config.instance().command_prefix}help` to get started.")
            return
        ctx.user = user

    @commands.command(aliases=TIPSTATS_INFO.triggers)
    async def tipstats_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user: User = ctx.user

        if await RedisDB.instance().exists(f"tipstatsspam{msg.author.id}{msg.guild.id}"):
            await Messages.send_error_dm(msg.author, "Why don't you wait awhile before trying to get your tipstats again")
            return

        stats: Stats = await user.get_stats(server_id=msg.guild.id)
        response = ""
        if stats is None or stats.total_tips == 0:
            response = "You haven't sent any tips in this server yet, tip some people and then check your stats later"
        else:
            response = f"You have sent {stats.total_tips} tips totaling {stats.total_tipped_amount} {Env.currency_symbol()}. Your biggest tip of all time is {stats.top_tip} {Env.currency_symbol()}"

        # TODO - no spam channels
        await msg.channel.send(response)
        await RedisDB.instance().set(f"tipstatsspam{msg.author.id}{msg.guild.id}", "as", expires=300)
