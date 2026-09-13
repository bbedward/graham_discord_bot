import discord

from util.env import Env

class Messages():
    @staticmethod
    async def respond_error(interaction: discord.Interaction, message: str, title: str = "Error"):
        embed = discord.Embed(colour=discord.Colour.red())
        embed.title = title
        embed.description = message
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            pass

    @staticmethod
    async def respond_success(interaction: discord.Interaction, message: str, header: str = "Success", footer: str = None, ephemeral: bool = True):
        embed = discord.Embed(colour=discord.Colour.green())
        embed.title = header
        embed.description = message
        if footer is not None:
            embed.set_footer(text=footer)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        except Exception:
            pass

    @staticmethod
    def tip_emoji(amount: float, rain: bool = False) -> str:
        if Env.banano():
            match amount:
                case a if a >= 250:
                    tier = '\U0001F98D'
                case a if a >= 50:
                    tier = '\U0001F412'
                case _:
                    tier = '\U0001F987'
        else:
            match amount:
                case a if a >= 1:
                    tier = '\U0001F40B'
                case a if a >= 0.5:
                    tier = '\U0001F988'
                case a if a >= 0.1:
                    tier = '\U0001F9AD'
                case a if a >= 0.01:
                    tier = '\U0001F980'
                case _:
                    tier = '\U0001F990'
        return f"{tier}\U0001F4A6" if rain else tier

    @staticmethod
    async def send_public(interaction: discord.Interaction, content: str = None, ack: str = "Done \U00002705", embed: discord.Embed = None):
        # Commands defer ephemerally so errors stay private; public output goes straight to the channel
        mentions = discord.AllowedMentions.none()
        try:
            await interaction.channel.send(content, embed=embed, allowed_mentions=mentions)
        except Exception:
            try:
                await interaction.followup.send(content, embed=embed, allowed_mentions=mentions)
            except Exception:
                pass
            return
        try:
            await interaction.followup.send(ack, ephemeral=True)
        except Exception:
            pass

    @staticmethod
    async def send_tip_line(interaction: discord.Interaction, amount: float, sender: discord.abc.User, targets: str, rain: bool = False):
        line = f"{Messages.tip_emoji(amount, rain=rain)} **{sender.display_name}** → {targets} ({Env.format_float(amount)} {Env.currency_symbol()})"
        await Messages.send_public(interaction, line, ack="Sent \U00002705")

    @staticmethod
    async def send_error_dm(member: discord.abc.User, message: str, skip_dnd=False) -> discord.Message:
        if member is None:
            return None
        if skip_dnd and getattr(member, 'status', None) == discord.Status.dnd:
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
    async def send_success_dm(member: discord.abc.User, message: str, header: str = "Success", footer: str = None, skip_dnd=False) -> discord.Message:
        if member is None:
            return None
        if skip_dnd and getattr(member, 'status', None) == discord.Status.dnd:
            return None
        embed = discord.Embed(colour=discord.Colour.green())
        embed.title = header
        embed.description = message
        if footer is not None:
            embed.set_footer(text=footer)
        try:
            return await member.send(embed=embed)
        except Exception:
            # May raise if user has blocked the bot
            return None

    @staticmethod
    async def send_basic_dm(member: discord.abc.User, message: str, skip_dnd=False) -> discord.Message:
        if member is None:
            return None
        if skip_dnd and getattr(member, 'status', None) == discord.Status.dnd:
            return None
        try:
            return await member.send(message)
        except Exception:
            # May raise if user has blocked the bot
            return None
