from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from models.constants import Constants
from util.env import Env

## Command(s) documentation
REGISTER_INFO = CommandInfo(
    triggers = ["deposit", "register", "wallet", "address"],
    overview = "Shows your account address",
    details = ("Displays your tip bot account address along with a QR code. QR code is encoded with an amount if provided" +
                f"\n- Send {'BANANO' if Env.banano() else 'Nano'} to this address to increase your tip bot balance" +
                "\n- If you do not have a tip bot account yet, this command will create one for you (receiving a tip automatically creates an account too)")
)

class Account(commands.Cog):
    def __init__(self, bot : Bot):
        self.bot = bot

    @commands.command(aliases=REGISTER_INFO.triggers)
    async def register_cmd(self, ctx : Context):
        message = ctx.message