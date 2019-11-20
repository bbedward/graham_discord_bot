import discord
from models.command import CommandInfo

class DM():
    @staticmethod
    async def post_usage(message: discord.Message, command : CommandInfo, prefix: str):
        embed = discord.Embed(colour=discord.Colour.purple())
        embed.title = "Usage:"
        embed.add_field(name=f"{prefix}command.triggers[0]", value=command.details, inline=False)
        await message.author.send(embed=embed)