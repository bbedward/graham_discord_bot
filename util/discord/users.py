import logging

import discord

logger = logging.getLogger()

async def resolve_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    member = guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except discord.NotFound:
        return None
    except discord.HTTPException:
        logger.debug(f"fetch_member failed for {user_id} in guild {guild.id}")
        return None

async def resolve_user(client: discord.Client, user_id: int) -> discord.User | None:
    user = client.get_user(user_id)
    if user is not None:
        return user
    try:
        return await client.fetch_user(user_id)
    except discord.HTTPException:
        logger.debug(f"fetch_user failed for {user_id}")
        return None
