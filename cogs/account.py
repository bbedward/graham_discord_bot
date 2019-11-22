import discord
from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from models.constants import Constants
from db.models.user import User
from util.conversions import BananoConversions, NanoConversions
from util.env import Env
from util.regex import RegexUtil
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages

import logging

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
        self.logger = logging.getLogger()

    @commands.command(aliases=REGISTER_INFO.triggers)
    async def register_cmd(self, ctx : Context):
        msg = ctx.message
        try:
            amount = RegexUtil.find_float(msg.content)
        except Exception:
            amount = 0.0
        # Get/create user
        try:
            user = await User.create_or_fetch_user(msg.author)
            await Messages.post_error_dm(msg.author, "I failed at retrieving your address, try again later and contact my master if the issue persists.")
        except Exception:
            self.logger.exception('Exception creating user')
        # Build URI
        uri_scheme = "ban:" if Env.banano() else "nano:"
        user_address = await user.account.address.first()
        if amount == 0:
            uri = user_address
        else:
            uri = "{0}{1}?amount={2}".format(uri_scheme, user_address, BananoConversions.banano_to_raw(amount) if Env.banano() else NanoConversions.nano_to_raw(amount))
        # Build and send response
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name=user_address, icon_url="https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/nano_logo.png")
        embed.set_image(url=f"https://chart.googleapis.com/chart?cht=qr&chl={uri}&chs=180x180&choe=UTF-8&chld=L|2")
        await msg.author.send(embed=embed)
        await msg.author.send(user_address)