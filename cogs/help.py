from cogs import tips, account, stats
from discord.ext import commands
from discord.ext.commands import Bot, Context
from util.env import Env
from util.discord.messages import Messages
from util.discord.paginator import Paginator, Page, CannotPaginate, Entry
from version import __version__

import config
import logging

COMMANDS = {
    'ACCOUNT': {
        'header': 'Account Commands',
        'info': 'Accounts that help you manage your Graham account',
        'cmd_list': [
            account.REGISTER_INFO,
            account.BALANCE_INFO,
            account.SEND_INFO,
            account.SENDMAX_INFO
        ]
    },
    'TIP': {
        'header': 'Tipping Commands',
        'info': 'The different ways you are able to tip with this bot',
        'cmd_list': [
            tips.TIP_INFO,
            tips.TIPSPLIT_INFO
        ]
    },
    'STATS': {
        'header': 'Statistics Commands',
        'info': 'The different statistics related to tips within the bot.',
        'cmd_list': [
            stats.TIPSTATS_INFO,
            stats.TOPTIPS_INFO
        ]
    }
}

class Help(commands.Cog):
    def __init__(self, bot: Bot, command_prefix: str):
        self.bot = bot
        self.logger = logging.getLogger()

    def get_entries(self, commands: list) -> list:
        entries = []
        for cmd in commands:
            entries.append(Entry(f"{config.Config.instance().command_prefix}{cmd.triggers[0]}", cmd.details))
        return entries

    def get_help_pages(self) -> list:
        """Builds paginated help menu"""
        pages = []
        # Overview
        author=f"Graham v{__version__} ({'BANANO' if Env.banano() else 'Nano'}) edition - by bbedward"
        title="Command Overview"
        description=("Use `{0}help command` for more information about a specific command " +
                " or go to the next page").format(config.Config.instance().command_prefix)
        entries = []
        for k, cmd_list in COMMANDS.items():
            for cmd in COMMANDS[k]['cmd_list']:
                entries.append(Entry(f"{config.Config.instance().command_prefix}{cmd.triggers[0]}", cmd.overview))
        pages.append(Page(entries=entries, title=title,author=author, description=description))
        # Build detail pages
        for group, details in COMMANDS.items():
            author=COMMANDS[group]['header']
            description=COMMANDS[group]['info']
            entries = self.get_entries(COMMANDS[group]['cmd_list'])
            pages.append(Page(entries=entries, author=author,description=description))
        # Info
        """
        entries = [paginator.Entry(TIP_AUTHOR['CMD'], TIP_AUTHOR['OVERVIEW'])]
        author=AUTHOR_HEADER + " - by bbedward"
        description=("**Reviews**:\n" + "'10/10 True Masterpiece' - That one guy" +
                "\n'0/10 Didn't get rain' - Almost everybody else\n\n" +
                "This bot is completely free to use and open source." +
                " Developed by bbedward (reddit: /u/bbedward, discord: bbedward#9246)" +
                "\nFeel free to send tips, suggestions, and feedback.\n\n" +
                "Representative Address: {0}\n\n"
                "github: https://github.com/bbedward/Graham_Nano_Tip_Bot").format(settings.representative)
        pages.append(paginator.Page(entries=entries, author=author,description=description))
        """
        return pages

    @commands.command()
    async def help(self, ctx: Context):
        """Show help menu or show info about a specific command"""
        msg = ctx.message
        # If they spplied an argument post usage for a specific command if applicable
        content = msg.content.split(' ')
        if len(content) > 1:
            arg = content[1].strip().lower()
            found = False
            for key, cmd in COMMANDS.items():
                for c in cmd['cmd_list']:
                    if arg in c.triggers:
                        found = True
                        await Messages.send_usage_dm(msg.author, c)
            if not found:
                await Messages.send_error_dm(msg.author, f'No such command: "**{arg}**"')
        else:
            try:
                pages = Paginator(self.bot, message=msg, page_list=self.get_help_pages(),as_dm=True)
                await pages.paginate(start_page=1)
            except CannotPaginate as e:
                self.logger.exception('Exception in paginator')

    @commands.command()
    async def adminhelp(self, ctx: Context):
        pass

