import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from db.models.transaction import Transaction
from db.models.user import User
from db.redis import RedisDB
from models.command import CommandInfo
from rpc.client import RPCClient
from tasks.transaction_queue import TransactionQueue
from util.discord.messages import Messages
from util.discord.resolver import InvalidAddressError, require_user, resolve, validate_address, validate_amount
from util.env import Env
from util.regex import RegexUtil, AddressAmbiguousException, AddressMissingException

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
    details = f"Displays the balance of your bot account (in {Env.currency_symbol()})." +
                f"\n - Available Balance represents the amount of {Env.currency_symbol()} that you have available to tip or withdraw." +
                f"\n - Pending Balance represents the amount of {Env.currency_symbol()} that has been sent or received, but not processed by the bot yet."
)
SEND_INFO = CommandInfo(
    triggers = ["send", "withdraw"],
    overview = f"Send {Env.currency_name()} to an external address.",
    details = f"Send specified amount to specified address." +
                f"\nExample `/send 10 {Env.currency_symbol().lower()}_3o7uzba8b9e1wqu5ziwpruteyrs3scyqr761x7ke6w1xctohxfh5du75qgaj` - Sends 10 {Env.currency_symbol()}"
)
SENDMAX_INFO = CommandInfo(
    triggers = ["sendmax", "withdrawmax"],
    overview = f"Send all of your {Env.currency_name()} to an external address.",
    details = f"Send entire balance to specified address." +
                f"\nExample `/sendmax {Env.currency_symbol().lower()}_3o7uzba8b9e1wqu5ziwpruteyrs3scyqr761x7ke6w1xctohxfh5du75qgaj` - Sends entire {Env.currency_symbol()} balance"
)

class AccountCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger()

    def parse_destination(self, address: str) -> str:
        try:
            destination = RegexUtil.find_address_match(address)
        except (AddressMissingException, AddressAmbiguousException):
            raise InvalidAddressError()
        return validate_address(destination)

    @app_commands.command(name="deposit", description=REGISTER_INFO.overview)
    @app_commands.describe(amount="Amount to encode in the deposit QR code")
    async def register_cmd(self, interaction: discord.Interaction, amount: float = 0.0):
        await interaction.response.defer(ephemeral=True)
        await resolve(interaction, require_registered=False, check_frozen=False)
        try:
            user = await User.create_or_fetch_user(interaction.user)
            user_address = await user.get_address()
        except Exception:
            self.logger.exception('Exception creating user')
            await Messages.respond_error(interaction, "I failed at retrieving your address, try again later and contact my master if the issue persists.")
            return
        uri_scheme = "ban:" if Env.banano() else "nano:"
        if amount == 0:
            uri = user_address
        else:
            uri = "{0}{1}?amount={2}".format(uri_scheme, user_address, Env.amount_to_raw(amount))
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name=user_address, icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
        embed.set_image(url=f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={uri}%20t&charset-source=utf-8")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await interaction.followup.send(user_address, ephemeral=True)

    def format_balance_message(self, balance_raw: int, pending_raw: int, pending_send_db: int, pending_receive_db: int) -> discord.Embed:
        embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
        embed.set_author(name="Balance", icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
        embed.description = "**Available:**\n"
        embed.description += f"```{Env.commafy(Env.format_float(Env.raw_to_amount(balance_raw - pending_send_db)))} {Env.currency_symbol()}\n"
        pending_receive_str = f"+ {Env.commafy(Env.format_float(Env.raw_to_amount(pending_raw + pending_receive_db)))} {Env.currency_symbol()}"
        pending_send_str = f"- {Env.commafy(Env.format_float(Env.raw_to_amount(pending_send_db)))} {Env.currency_symbol()}"
        rjust_size = max(len(pending_send_str), len(pending_receive_str))
        embed.description += f"{pending_receive_str.ljust(rjust_size)} (Pending Receipt)\n{pending_send_str.ljust(rjust_size)} (Pending Send)```\n"
        embed.set_footer(text="Pending balances are in queue and will become available after processing.")
        return embed

    @app_commands.command(name="balance", description=BALANCE_INFO.overview)
    async def balance_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        inv = await resolve(interaction, check_frozen=False)
        user = inv.user
        try:
            address = await user.get_address()
            balance_json = await RPCClient.instance().account_balance(address, False)
            if balance_json is None:
                raise Exception("balance_json was None")
            balance_raw = int(balance_json['balance'])
            pending_raw = int(balance_json['pending'])
            # Consider unprocessed amounts as well
            pending_send_db, pending_receive_db = await user.get_pending()
            embed = self.format_balance_message(balance_raw, pending_raw, pending_send_db, pending_receive_db)
            sent = await interaction.followup.send(embed=embed, ephemeral=True, wait=True)
            if pending_raw >= 1000000000000000000000000000:
                # Pocket some transactions and update their balance
                asyncio.ensure_future(
                    self.pocket_pendings(
                        sent,
                        address,
                        user
                    )
                )
        except Exception:
            self.logger.exception("Unavailble to retrieve user from database")
            await Messages.respond_error(interaction, "I was unable to retrieve your balance, try again later.")

    async def pocket_pendings(self, msg: discord.Message, address: str, dbuser: User):
        """Pocket some pending transactions and edit the users message"""
        # Check if they've done this recently to avoid spam
        if await RedisDB.instance().exists(f"pocketpendingspam:{dbuser.id}"):
            return
        # Check for pendings
        pendings = await RPCClient.instance().pending(address)
        should_update_balance = False
        if pendings is None or len(pendings) == 0:
            return
        # Update spam flag
        await RedisDB.instance().set(f"pocketpendingspam:{dbuser.id}", "as", expires=60)
        # Pocket pendings
        for p in pendings:
            if await RPCClient.instance().receive(address, p) is not None:
                should_update_balance = True
        # Update their balance message
        if should_update_balance:
            balance_json = await RPCClient.instance().account_balance(address, True)
            if balance_json is None:
                raise Exception("balance_json was None")
            balance_raw = int(balance_json['balance'])
            pending_raw = int(balance_json['pending'])
            pending_send_db, pending_receive_db = await dbuser.get_pending()
            balance_msg = self.format_balance_message(balance_raw, pending_raw, pending_send_db, pending_receive_db)
            await msg.edit(embed=balance_msg)

    @app_commands.command(name="send", description=SEND_INFO.overview)
    @app_commands.describe(amount="Amount to send", address=f"External {Env.currency_name()} address to send to")
    async def send_cmd(self, interaction: discord.Interaction, amount: float, address: str):
        await interaction.response.defer(ephemeral=True)
        inv = await require_user(interaction)
        validate_amount(amount, minimum=0.01 if Env.banano() else 0.000001)
        destination = self.parse_destination(address)
        user = inv.user

        withdraw_delay = await user.get_next_withdraw_s()
        if withdraw_delay > 0:
            await Messages.respond_error(interaction, f"You need to wait {withdraw_delay}s before you can withdraw again")
            return

        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount > available_balance:
            await Messages.respond_error(interaction, f"Your balance isn't high enough to complete this transaction. You have **{available_balance} {Env.currency_symbol()}**, but this would cost you **{amount} {Env.currency_symbol()}**")
            return

        tx = await Transaction.create_transaction_external(
            sending_user=user,
            amount=amount,
            destination=destination
        )
        await TransactionQueue.instance().put(tx)
        await Messages.respond_success(interaction, "I've queued your transaction! I'll let you know once I broadcast it to the network.")

    @app_commands.command(name="sendmax", description=SENDMAX_INFO.overview)
    @app_commands.describe(address=f"External {Env.currency_name()} address to send to")
    async def sendmax_cmd(self, interaction: discord.Interaction, address: str):
        await interaction.response.defer(ephemeral=True)
        inv = await require_user(interaction)
        destination = self.parse_destination(address)
        user = inv.user

        withdraw_delay = await user.get_next_withdraw_s()
        if withdraw_delay > 0:
            await Messages.respond_error(interaction, f"You need to wait {withdraw_delay}s before you can withdraw again")
            return

        bal = await user.get_available_balance_dec()
        if (bal < 0.01 and Env.banano()) or (bal < 0.000001 and not Env.banano()):
            await Messages.respond_error(interaction, "You balance is 0, so I can't make any withdraw")
            return

        tx = await Transaction.create_transaction_external(
            sending_user=user,
            amount=None,
            raw_amt=str(await user.get_available_balance()),
            destination=destination
        )
        await TransactionQueue.instance().put(tx)
        await Messages.respond_success(interaction, "I've queued your transaction! I'll let you know once I broadcast it to the network.")
