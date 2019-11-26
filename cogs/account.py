import discord
from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from models.constants import Constants
from db.models.account import Account
from db.models.transaction import Transaction
from db.models.user import User
from rpc.client import RPCClient
from tasks.transaction_queue import TransactionQueue
from util.env import Env
from util.regex import RegexUtil, AmountMissingException, AmountAmbiguousException, AddressAmbiguousException, AddressMissingException
from util.validators import Validators
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages

import config
import logging

## Command(s) documentation
REGISTER_INFO = CommandInfo(
    triggers = ["deposit", "register", "wallet", "address"],
    overview = "Shows your account address",
    details = "Displays your tip bot account address along with a QR code. QR code is encoded with an amount if provided" +
                f"\n- Send {Env.currency_name()} to this address to increase your tip bot balance" +
                "\n- If you do not have a tip bot account yet, this command will create one for you (receiving a tip automatically creates an account too)"
)
BALANCE_INFO = CommandInfo(
    triggers = ["balance", "bal", "$"],
    overview = "Shows your account balance",
    details = f"Displays the balance of your tipbot account (in {Env.currency_symbol()})." +
                f"\n - Available Balance represents the amount of {Env.currency_symbol()} that you have available to tip or withdraw." +
                f"\n - Pending Balance represents the amount of {Env.currency_symbol()} that has been sent or received, but not processed by the bot yet."
)
SEND_INFO = CommandInfo(
    triggers = ["send", "withdraw"],
    overview = f"Send {Env.currency_name()} to an external address.",
    details = f"Send specified amount to specified address." +
                f"\nExample `{config.Config.instance().command_prefix}send 10 {Env.currency_symbol().lower()}_3o7uzba8b9e1wqu5ziwpruteyrs3scyqr761x7ke6w1xctohxfh5du75qgaj - Sends 10 {Env.currency_symbol()}"
)
SENDMAX_INFO = CommandInfo(
    triggers = ["sendmax", "withdrawmax"],
    overview = f"Send all of your {Env.currency_name()} to an external address.",
    details = f"Send entire balance to specified address." +
                f"\nExample `{config.Config.instance().command_prefix}sendmax {Env.currency_symbol().lower()}_3o7uzba8b9e1wqu5ziwpruteyrs3scyqr761x7ke6w1xctohxfh5du75qgaj - Sends entire {Env.currency_symbol()} balance"
)

class Account(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.logger = logging.getLogger()

    async def cog_before_invoke(self, ctx: Context):
        # TODO - check paused, frozen
        if ctx.command.name == 'send_cmd':
            try:
                ctx.send_amount = RegexUtil.find_send_amounts(ctx.message.content)
            except AmountMissingException:
                await Messages.send_usage_dm(ctx.message.author, SEND_INFO)
                raise Exception(f"AmountMissingException {ctx.command.name}")
            except AmountAmbiguousException:
                await Messages.send_error_dm(ctx.message.author, "You can only specify 1 amount to send")
                raise Exception(f"AmountAmbiguousException {ctx.command.name}")
        if ctx.command.name in ['send_cmd', 'sendmax_cmd']:
            # See if user exists in DB
            user = await User.get_user(ctx.message.author)
            if user is None:
                ctx.error = True
                await Messages.send_error_dm(ctx.message.author, f"You should create an account with me first, send me `{config.Config.instance().command_prefix}help` to get started.")
                raise Exception(f"invoked command {ctx.command.name} without creating account")
            ctx.user = user
            try:
                ctx.destination = RegexUtil.find_address_match(ctx.message.content)
            except AddressMissingException:
                await Messages.send_usage_dm(ctx.message.author, SEND_INFO)
                raise Exception(f"AddressMissingException {ctx.command.name}")
            except AddressAmbiguousException:
                await Messages.send_error_dm(ctx.message.author, "You can only specify 1 destination address")
                raise Exception(f"AddressAmbiguousException {ctx.command.name}")
            if not Validators.is_valid_address(ctx.destination):
                await Messages.send_error_dm(ctx.message.author, "The destination address you specified is invalid")
                raise Exception(f"Invalid address {ctx.command.name} {ctx.destination}")                

    @commands.command(aliases=REGISTER_INFO.triggers)
    async def register_cmd(self, ctx: Context):
        msg = ctx.message
        try:
            amount = RegexUtil.find_float(msg.content)
        except AmountMissingException:
            amount = 0.0
        # Get/create user
        try:
            user = await User.create_or_fetch_user(msg.author)
            user_address = await user.get_address()
        except Exception:
            self.logger.exception('Exception creating user')
            await Messages.send_error_dm(msg.author, "I failed at retrieving your address, try again later and contact my master if the issue persists.")
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
    async def balance_cmd(self, ctx: Context):
        msg = ctx.message
        try:
            user = await User.get_user(msg.author)
            if user is None:
                await Messages.send_error_dm(msg.author, f"It looks like you haven't created an account yet, you should use `{config.Config.instance().command_prefix}register` to create one.")
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
            await Messages.send_error_dm(msg.author, "I was unable to retrieve your balance, try again later.")

    @commands.command(aliases=SEND_INFO.triggers)
    async def send_cmd(self, ctx: Context):
        msg = ctx.message

        user: User = ctx.user
        send_amount: float = ctx.send_amount
        destination: str = ctx.destination

        # See if they are spammin'
        withdraw_delay = await user.get_next_withdraw_s()
        if withdraw_delay > 0:
            await Messages.send_error_dm(msg.author, f"You need to wait {int(withdraw_delay)}s before you can withdraw again")

        # Create transaction
        tx = await Transaction.create_transaction_external(
            sending_user=user,
            amount=send_amount,
            destination=destination
        )
        # Queue the actual send
        await TransactionQueue.instance().put(tx)
        # Send user message
        await Messages.send_success_dm(msg.author, "I've queued your transaction! I'll let you know once I broadcast it to the network.")

    @commands.command(aliases=SENDMAX_INFO.triggers)
    async def sendmax_cmd(self, ctx: Context):
        msg = ctx.message

        user: User = ctx.user
        destination: str = ctx.destination

        # See if they are spammin'
        withdraw_delay = await user.get_next_withdraw_s()
        if withdraw_delay > 0:
            await Messages.send_error_dm(msg.author, f"You need to wait {int(withdraw_delay)}s before you can withdraw again")

        # Create transaction
        tx = await Transaction.create_transaction_external(
            sending_user=user,
            amount=await user.get_available_balance_dec(),
            destination=destination
        )
        # Queue the actual send
        await TransactionQueue.instance().put(tx)
        # Send user message
        await Messages.send_success_dm(msg.author, "I've queued your transaction! I'll let you know once I broadcast it to the network.")