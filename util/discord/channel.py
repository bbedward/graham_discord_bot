import discord


class ChannelUtil():
    @staticmethod
    def is_private(channel) -> bool:
        return isinstance(channel, discord.abc.PrivateChannel)

