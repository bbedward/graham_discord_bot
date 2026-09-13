import discord
from discord import app_commands
from discord.ext import commands

from db.models.account import Account
from db.models.user import User
from models.command import CommandInfo
from util.discord.messages import Messages
from util.discord.resolver import require_admin
from util.env import Env
from util.regex import RegexUtil, AddressMissingException

# Commands Documentation
WFU_INFO = CommandInfo(
    triggers = ["wfu", "walletfor", "walletforuser"],
    overview = "Get address for a particular user.",
    details = "This will show information a about a user's account"
)
UFW_INFO = CommandInfo(
    triggers = ["ufw", "userfor", "userforwallet"],
    overview = "Get user info from a particular address",
    details = "This will show information about a user's account"
)

def spy_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(colour=0xFBDD11 if Env.banano() else discord.Colour.dark_blue())
    embed.set_author(name=title, icon_url="https://github.com/bbedward/graham_discord_bot/raw/master/assets/banano_logo.png" if Env.banano() else "https://github.com/bbedward/graham_discord_bot/raw/master/assets/nano_logo.png")
    embed.description = description
    return embed

def account_summary(name: str, user_id: int, address: str) -> str:
    explorer = f"https://creeper.banano.cc/explorer/account/{address}" if Env.banano() else f"https://blocklattice.io/account/{address}"
    return f"Last known name: {name}```{user_id}```" + f"```{address}```" + explorer + "\n"

class SpyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="wfu", description=WFU_INFO.overview)
    @app_commands.describe(user="The user to look up")
    async def wfu_cmd(self, interaction: discord.Interaction, user: discord.User):
        await require_admin(interaction)
        db_user = await User.filter(id=user.id).prefetch_related('account').first()
        if db_user is None:
            await Messages.respond_error(interaction, "That user doesn't have an account with me")
            return
        response = account_summary(db_user.name, db_user.id, db_user.account.address)
        await interaction.response.send_message(embed=spy_embed("WFU Result", response), ephemeral=True)

    @app_commands.command(name="ufw", description=UFW_INFO.overview)
    @app_commands.describe(address=f"The {Env.currency_name()} address to look up")
    async def ufw_cmd(self, interaction: discord.Interaction, address: str):
        await require_admin(interaction)
        try:
            addresses = RegexUtil.find_address_matches(address)
        except AddressMissingException:
            await Messages.respond_error(interaction, "No valid addresses in your ufw command")
            return
        address_list = await Account.filter(address__in=addresses).prefetch_related('user').all()
        if len(address_list) < 1:
            await Messages.respond_error(interaction, "No users found with specified addresses.")
            return
        response = ''.join(account_summary(acct.user.name, acct.user.id, acct.address) for acct in address_list)
        await interaction.response.send_message(embed=spy_embed("UFW Result", response), ephemeral=True)
