from discord.ext import commands, Bot
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from models.constants import Constans
from util.env import Env

class Tips(commands.Cog):
    def __init__(self, bot : Bot):
        self.bot = bot

    TIP_INFO = CommandInfo(
        triggers = ["ban", "b"] if settings.banano else ["ntip", "n"],
        overview = "Send a tip to mentioned users",
        details = f"Tip specified amount to mentioned user(s) (minimum tip is {Constants.TIP_MINIMUM} {Constants.TIP_UNIT})" +
            "\nThe recipient(s) will be notified of your tip via private message" +
            "\nSuccessful tips will be deducted from your available balance immediately.",
        example = f"{'ban' if Env.banano() else 'ntip'} 2 @user1 @user2` would send 2 to user1 and 2 to user2"
    )
    @commands.command()
    async def tip_cmd(self, ctx : Context):
        message = ctx.message