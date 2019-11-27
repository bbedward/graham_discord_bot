import config
import discord
from models.command import CommandInfo
from util.env import Env

class Messages():
    @staticmethod
    async def send_usage_dm(member: discord.Member, command: CommandInfo) -> discord.Message:
        embed = discord.Embed(colour=discord.Colour.purple())
        embed.title = "Usage"
        embed.add_field(name=f"{config.Config.instance().command_prefix}{command.triggers[0]}", value=command.details, inline=False)
        try:
            return await member.send(embed=embed)
        except Exception:
            # May raise if user has blocked the bot
            return None
 
    @staticmethod
    async def send_error_dm(member: discord.Member, message: str, skip_dnd=False) -> discord.Message:
        if skip_dnd and member.status == discord.Status.dnd:
            return None
        embed = discord.Embed(colour=discord.Colour.red())
        embed.title = "Error"
        embed.description = message
        try:
            return await member.send(embed=embed)
        except Exception:
            # May raise if user has blocked the bot
            return None

    @staticmethod
    async def send_success_dm(member: discord.Member, message: str, skip_dnd=False) -> discord.Message:
        if skip_dnd and member.status == discord.Status.dnd:
            return None
        embed = discord.Embed(colour=discord.Colour.green())
        embed.title = "Success"
        embed.description = message
        try:
            return await member.send(embed=embed)
        except Exception:
            # May raise if user has blocked the bot
            return None

    @staticmethod
    async def send_basic_dm(member: discord.Member, message: str, skip_dnd=False) -> discord.Message:
        if skip_dnd and member.status == discord.Status.dnd:
            return None
        try:
            return await member.send(message)
        except Exception:
            # May raise if user has blocked the bot
            return None

    @staticmethod
    async def add_tip_reaction(msg: discord.Message, amount: float):
        if Env.banano():
            if amount > 0:
                await msg.add_reaction('\:tip:425878628119871488') # TIP mark
                await msg.add_reaction('\:tick:425880814266351626') # check mark
            if amount > 0 and amount < 50:
                await msg.add_reaction('\U0001F987') # S
            elif amount >= 50 and amount < 250:
                await msg.add_reaction('\U0001F412') # C
            elif amount >= 250:
                await msg.add_reaction('\U0001F98D') # W
        else:
            if amount > 0:
                await msg.add_reaction('\U00002611') # check mark
            if amount > 0 and amount < 0.01:
                await msg.add_reaction('\U0001F1F8') # S
                await msg.add_reaction('\U0001F1ED') # H
                await msg.add_reaction('\U0001F1F7') # R
                await msg.add_reaction('\U0001F1EE') # I
                await msg.add_reaction('\U0001F1F2') # M
                await msg.add_reaction('\U0001F1F5') # P
            elif amount >= 0.01 and amount < 0.1:
                await msg.add_reaction('\U0001F1E8') # C
                await msg.add_reaction('\U0001F1F7') # R
                await msg.add_reaction('\U0001F1E6') # A
                await msg.add_reaction('\U0001F1E7') # B
            elif amount >= 0.1 and amount < 0.5:
                await msg.add_reaction('\U0001F1FC') # W
                await msg.add_reaction('\U0001F1E6') # A
                await msg.add_reaction('\U0001F1F1') # L
                await msg.add_reaction('\U0001F1F7') # R
                await msg.add_reaction('\U0001F1FA') # U
                await msg.add_reaction('\U0001F1F8') # S
            elif amount >= 0.5 and amount < 1:
                await msg.add_reaction('\U0001F1F8') # S
                await msg.add_reaction('\U0001F1ED') # H
                await msg.add_reaction('\U0001F1E6') # A
                await msg.add_reaction('\U0001F1F7') # R
                await msg.add_reaction('\U0001F1F0') # K
            elif amount >= 1:
                await msg.add_reaction('\U0001F1F2') # M
                await msg.add_reaction('\U0001F1EA') # E
                await msg.add_reaction('\U0001F1EC') # G
                await msg.add_reaction('\U0001F1E6') # A
                await msg.add_reaction('\U0001F1F1') # L
                await msg.add_reaction('\U0001F1E9') # D
                await msg.add_reaction('\U0001F1F4') # O
                await msg.add_reaction('\U0001F1F3') # N

    @staticmethod
    async def add_x_reaction(msg: discord.Message):
        await msg.add_reaction('\U0000274C') # X
        return