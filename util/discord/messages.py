import discord
from models.command import CommandInfo

class Messages():
    @staticmethod
    async def post_usage_dm(message: discord.Message, command : CommandInfo, prefix: str):
        embed = discord.Embed(colour=discord.Colour.purple())
        embed.title = "Usage:"
        embed.add_field(name=f"{prefix}command.triggers[0]", value=command.details, inline=False)
        await message.author.send(embed=embed)
 
    @staticmethod
    async def post_error_dm(member : discord.Member, message : str, skip_dnd=False):
        embed = discord.Embed(colour=discord.Colour.red())
        embed.title = "Error:"
        embed.description = message
        await member.send(message)