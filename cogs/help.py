import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs import account, admin, favorites, giveaway, rain, spy, stats, tips, useroptions
from util.discord.messages import Messages
from util.discord.paginator import CannotPaginate, Entry, Page, Paginator
from util.discord.resolver import resolve
from util.env import Env
from version import __version__

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
            tips.TIPSPLIT_INFO,
            tips.TIPRANDOM_INFO,
            rain.RAIN_INFO,
            favorites.TIPFAVORITES_INFO
        ]
    },
    'GIVEAWAY': {
        'header': 'Giveaway Commands',
        'info': 'How to create and participate in giveaways',
        'cmd_list': [
            giveaway.START_GIVEAWAY_INFO,
            giveaway.TICKET_INFO,
            giveaway.TICKETSTATUS_INFO,
            giveaway.TIPGIVEAWAY_INFO,
            giveaway.GIVEAWAYSTATS_INFO
        ]
    },
    'STATS': {
        'header': 'Statistics Commands',
        'info': 'The different statistics related to tips within the bot.',
        'cmd_list': [
            stats.TIPSTATS_INFO,
            stats.TOPTIPS_INFO,
            stats.LEADERBOARD_INFO,
            stats.LEGACYBOARD_INFO,
            giveaway.WINNERS_INFO
        ]
    },
    'USER_OPTIONS': {
        'header': 'User Options Commands',
        'info': 'Various user-specific options.',
        'cmd_list': [
            useroptions.MUTE_INFO,
            useroptions.UNMUTE_INFO,
            favorites.ADD_FAVORITE_INFO,
            favorites.REMOVE_FAVORITE_INFO,
            favorites.FAVORITES_INFO
        ]
    },
}

ADMIN_COMMANDS = {
    'ADMIN': {
        'header': 'ADMIN Commands',
        'info': 'The different commands admin can use to manage the bot.',
        'cmd_list': [
            admin.PAUSE_INFO,
            admin.RESUME_INFO,
            admin.FREEZE_INFO,
            admin.DEFROST_INFO,
            admin.FROZEN_INFO,
            admin.TIPBAN_INFO,
            admin.TIPUNBAN_INFO,
            admin.TIPBANNED_INFO,
            admin.STATSBAN_INFO,
            admin.STATSUNBAN_INFO,
            admin.STATSBANNED_INFO,
            admin.DECREASETIPS_INFO,
            admin.INCREASETIPS_INFO,
            spy.WFU_INFO,
            spy.UFW_INFO
        ]
    }
}

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger()

    def get_entries(self, cmd_list: list) -> list:
        return [Entry(f"/{cmd.triggers[0]}", cmd.details) for cmd in cmd_list]

    def get_help_pages(self, cmd_dict: dict) -> list:
        """Builds paginated help menu"""
        pages = []
        # Overview
        author=f"Graham v{__version__} ({'BANANO' if Env.banano() else 'Nano'}) edition"
        title="Command Overview"
        description="Use `/help command:<name>` for more information about a specific command, or go to the next page"
        entries = []
        for k in cmd_dict:
            for cmd in cmd_dict[k]['cmd_list']:
                entries.append(Entry(f"/{cmd.triggers[0]}", cmd.overview))
        pages.append(Page(entries=entries, title=title, author=author, description=description))
        # Build detail pages
        for group, details in cmd_dict.items():
            pages.append(Page(entries=self.get_entries(details['cmd_list']), author=details['header'], description=details['info']))
        # Info
        entries = [Entry(f"/{tips.TIPAUTHOR_INFO.triggers[0]}", tips.TIPAUTHOR_INFO.details)]
        author=f"Graham v{__version__} for {Env.currency_name()}"
        heart = '\U0001F49B' if Env.banano() else '\U0001F499'
        description = "This bot is completely free, open source, and MIT licensed"
        description+= f"\n\nMade with {heart} for the **BANANO** and **NANO** communities"
        description+= f"\nHangout with some awesome people at https://chat.banano.cc"
        description+= f"\nMy Discord: **@bbedward#9246**"
        description+= f"\nMy Reddit: **/u/bbedward**"
        description+= f"\nMy Twitter: **@theRealBbedward**"
        description+= f"\n\nGraham GitHub: https://github.com/bbedward/graham_discord_bot"
        pages.append(Page(entries=entries, author=author, description=description))
        return pages

    @app_commands.command(name="help", description="Show the help menu or info about a specific command")
    @app_commands.describe(command="The command to show detailed help for")
    async def help_cmd(self, interaction: discord.Interaction, command: str = None):
        inv = await resolve(interaction, check_paused=False, require_registered=False)
        cmd_dicts = [COMMANDS, ADMIN_COMMANDS] if inv.admin else [COMMANDS]

        if command is not None:
            arg = command.strip().lower().lstrip('/')
            for cmd_dict in cmd_dicts:
                for key, cmd in cmd_dict.items():
                    for c in cmd['cmd_list']:
                        if arg in c.triggers:
                            embed = discord.Embed(colour=discord.Colour.purple())
                            embed.title = "Usage"
                            embed.add_field(name=f"/{c.triggers[0]}", value=c.details, inline=False)
                            await interaction.response.send_message(embed=embed, ephemeral=True)
                            return
            await Messages.respond_error(interaction, f'No such command: "**{arg}**"')
            return

        pages = self.get_help_pages(COMMANDS)
        if inv.admin:
            pages += self.get_help_pages(ADMIN_COMMANDS)
        try:
            await Paginator.send_as_response(interaction, pages, ephemeral=True)
        except CannotPaginate:
            self.logger.exception('Exception in paginator')
