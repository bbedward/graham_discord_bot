import discord
from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from models.constants import Constants
from db.models.account import Account
from db.models.transaction import Transaction
from db.models.user import User
from rpc.client import RPCClient
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
                f"\n- Send {Env.currency_name()} to this address to increase your tip bot balance" +
                "\n- If you do not have a tip bot account yet, this command will create one for you (receiving a tip automatically creates an account too)")
)
BALANCE_INFO = CommandInfo(
    triggers = ["balance", "bal", "$"],
    overview = "Shows your account balance",
    details = (f"Displays the balance of your tipbot account (in {Env.currency_symbol()})." +
                f"\n - Available Balance represents the amount of {Env.currency_symbol()} that you have available to tip or withdraw." +
                f"\n - Pending Balance represents the amount of {Env.currency_symbol()} that has been sent or received, but not processed by the bot yet.")

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
            uri = "{0}{1}?amount={2}".format(uri_scheme, user_address, Env.amount_to_raw(amount))
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
            # Get "actual" balance
            balance_json = await RPCClient.instance().account_balance(await user.get_address())
            if balance_json is None:
                raise Exception("balance_json was None")
            balance_raw = int(balance_json['balance'])
            pending_raw = int(balance_json['pending'])
            # Consider unprocessed amounts as well
            pending_send_db, pending_receive_db = await user.get_pending()
            embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
            embed.set_author(name="Balance", icon_url="https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/Graham_Nano_Tip_Bot/raw/master/assets/nano_logo.png")
            embed.description = "**Available:**\n"
            embed.description += f"{str(Env.raw_to_amount(balance_raw))} {Env.currency_symbol()}\n"
            embed.description += "**Pending Send:**\n"
            embed.description += f"{str(Env.raw_to_amount(pending_raw + pending_send_db))} {Env.currency_symbol()}\n"
            embed.description += "**Pending Receive:**\n"
            embed.description += f"{str(Env.raw_to_amount(pending_raw + pending_receive_db))} {Env.currency_symbol()}"
            embed.set_footer(text="Pending balances are in queue and will become available after processing.")
            await msg.author.send(embed=embed)            
        except Exception:
            self.logger.exception("Unavailble to retrieve user from database")
            await Messages.post_error_dm(msg.author, "I was unable to retrieve your balance, try again later.")