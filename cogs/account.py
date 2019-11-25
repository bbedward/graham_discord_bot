import discord
from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from models.constants import Constants
from db.models.account import Account
from db.models.user import User
from rpc.client import RPCClient
from util.conversions import BananoConversions, NanoConversions
from util.env import Env
from util.regex import RegexUtil
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages

import config
import logging

## Command(s) documentation
REGISTER_INFO = CommandInfo(
    triggers = ["deposit", "register", "wallet", "address"],
    overview = "Shows your account address",
    details = ("Displays your tip bot account address along with a QR code. QR code is encoded with an amount if provided" +
                f"\n- Send {'BANANO' if Env.banano() else 'Nano'} to this address to increase your tip bot balance" +
                "\n- If you do not have a tip bot account yet, this command will create one for you (receiving a tip automatically creates an account too)")
)
BALANCE_INFO = CommandInfo(
    triggers = ["balance", "bal", "$"],
    overview = "Shows your account balance",
    details = (f"Displays the balance of your tipbot account (in {'BAN' if Env.banano() else 'Nano'})." +
                f"\n - Available Balance represents the amount of {'BANANO' if Env.banano() else 'Nano'} that you have available to tip or withdraw." +
                f"\n - Pending Balance represents the amount of {'BANANO' if Env.banano() else 'Nano'} that has been sent or received, but not processed by the bot yet.")

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
            user_address = await user.get_address()
        except Exception:
            self.logger.exception('Exception creating user')
            await Messages.post_error_dm(msg.author, "I failed at retrieving your address, try again later and contact my master if the issue persists.")
            return
        # Build URI
        uri_scheme = "ban:" if Env.banano() else "nano:"
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

    @commands.command(aliases=BALANCE_INFO.triggers)
    async def balance_cmd(self, ctx : Context):
        msg = ctx.message
        try:
            user = await User.get_user(msg.author)
            if user is None:
                await Messages.post_error_dm(msg.author, f"It looks like you haven't created an account yet, you should use `{config.Config.instance().command_prefix}register` to create one.")
                return
            balance_json = await RPCClient.instance().account_balance(await user.get_address())
            if balance_json is None:
                raise Exception("balance_json was None")
            # TODO - also consider unprocessed transactions
            balance_raw = int(balance_json['balance'])
            pending_raw = int(balance_json['pending'])
            embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
            embed.set_author(name="Balance", icon_url="https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/nano_logo.png")
            embed.add_field(name="**Available:**", value=f"`{str(BananoConversions.raw_to_banano(balance_raw)) + ' BAN' if Env.banano() else str(NanoConversions.raw_to_nano(balance_raw)) + ' Nano'}`", inline=False)
            embed.add_field(name="**Pending:**", value=f"`{str(BananoConversions.raw_to_banano(pending_raw)) + ' BAN' if Env.banano() else str(NanoConversions.raw_to_nano(pending_raw)) + ' Nano'}`", inline=False)
            embed.set_footer(text="Pending balances are in queue and will become available after processing.")
            await msg.author.send(embed=embed)            
        except Exception:
            self.logger.exception("Unavailble to retrieve user from database")
            await Messages.post_error_dm(msg.author, "I was unable to retrieve your balance, try again later.")