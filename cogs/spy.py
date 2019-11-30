from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo
from util.discord.messages import Messages
from util.regex import RegexUtil, AddressMissingException
from db.models.account import Account
from db.models.user import User

# Commands Documentation
WFU_INFO = CommandInfo(
    triggers = ["wfu", "walletfor", "walletforuser"],
    overview = "Get address for a particular user.",
    details = f"This will show information a about a user's account"
)
UFW_INFO = CommandInfo(
    triggers = ["ufw", "userfor", "userforwallet"],
    overview = "Get user info from a particular address",
    details = f"This will show information about a user's account"
)

class SpyCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command(aliases=WFU_INFO.triggers)
    async def wfu_cmd(self, ctx: Context):
        msg = ctx.message

        targets = []
        # Get mentioned users
        for m in msg.mentions:
            targets.append(m.id)
    
        # Get users they are spying on by ID alone
        for sec in msg.content.split():
            try:
                numeric = int(sec.strip())
                user = await self.bot.fetch_user(numeric)
                if user is not None:
                    targets.append(user.id)
            except Exception:
                pass
        targets = set(targets)

        if len(targets) < 1:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "No valid users in your wfu command")
            return

        user_list = await User.filter(id__in=targets).prefetch_related('account').all()
        if len(user_list) < 1:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "None of those users have accounts with me")
            return

        for u in user_list:
            response = f"Last known name: {u.name}```{u.id}```"
            response += f"```{u.account.address}```"
            response += f"https://creeper.banano.cc/explorer/account/{u.account.address}\n"

        await msg.author.send(response)

    @commands.command(aliases=UFW_INFO.triggers)
    async def ufw_cmd(self, ctx: Context):
        msg = ctx.message

        try:
            addresses = RegexUtil.find_address_matches(msg.content)
        except AddressMissingException:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "No valid addresses in your ufw command")
            return
    
        address_list = await Account.filter(address__in=addresses).prefetch_related('user').all()
        if len(address_list) < 1:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "No users found with specified addresses.")
            return

        for acct in address_list:
            response = f"Last known name: {acct.user.name}```{acct.user.id}```"
            response += f"```{acct.address}```"
            response += f"https://creeper.banano.cc/explorer/account/{acct.address}\n"

        await msg.author.send(response)