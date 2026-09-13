from dataclasses import dataclass

import discord
from discord import app_commands

import config
from db.models.user import User
from db.redis import RedisDB
from util.env import Env
from util.validators import Validators

class PausedError(app_commands.CheckFailure):
    def __init__(self):
        super().__init__("Transaction activity is currently suspended. I'll be back online soon!")

class NotRegisteredError(app_commands.CheckFailure):
    def __init__(self):
        super().__init__("You should create an account with me first, use `/deposit` to get started.")

class FrozenError(app_commands.CheckFailure):
    def __init__(self):
        super().__init__("Your account is frozen. Contact an admin if you need further assistance.")

class NotAdminError(app_commands.CheckFailure):
    def __init__(self):
        super().__init__("You don't have permission to do that.")

class AmountPrecisionError(app_commands.CheckFailure):
    def __init__(self):
        super().__init__(f"You are only allowed to use {Env.precision_digits()} digits after the decimal.")

class AmountTooSmallError(app_commands.CheckFailure):
    def __init__(self, minimum: float):
        super().__init__(f"The minimum amount for this command is {minimum} {Env.currency_symbol()}")

class InvalidAddressError(app_commands.CheckFailure):
    def __init__(self):
        super().__init__("The destination address you specified is invalid.")

@dataclass(frozen=True)
class Invocation:
    interaction: discord.Interaction
    user: User
    god: bool
    admin: bool

def is_god(user_id: int) -> bool:
    return user_id in config.Config.instance().get_admin_ids()

def is_admin(interaction: discord.Interaction) -> bool:
    admin_roles = config.Config.instance().get_admin_roles()
    if not admin_roles:
        return False
    # Interaction payloads carry the invoker's member roles without any intent
    if isinstance(interaction.user, discord.Member):
        if any(role.id in admin_roles for role in interaction.user.roles):
            return True
    # Admin role in any shared guild grants admin everywhere, matching the
    # pre-slash behavior; the cache scan only works with the members intent
    for guild in interaction.client.guilds:
        member = guild.get_member(interaction.user.id)
        if member is None:
            continue
        for role in member.roles:
            if role.id in admin_roles:
                return True
    return False

async def resolve(interaction: discord.Interaction, *, check_paused: bool = True, require_registered: bool = True, check_frozen: bool = True) -> Invocation:
    if check_paused and await RedisDB.instance().is_paused():
        raise PausedError()

    user = await User.get_user(interaction.user)
    if require_registered and user is None:
        raise NotRegisteredError()
    if check_frozen and user is not None and user.frozen:
        raise FrozenError()
    if user is not None:
        await user.update_name(interaction.user.name)

    return Invocation(
        interaction=interaction,
        user=user,
        god=is_god(interaction.user.id),
        admin=is_admin(interaction)
    )

async def require_user(interaction: discord.Interaction) -> Invocation:
    return await resolve(interaction)

async def require_admin(interaction: discord.Interaction) -> Invocation:
    inv = await resolve(interaction, check_paused=False, require_registered=False)
    if not inv.god and not inv.admin:
        raise NotAdminError()
    return inv

def validate_amount(amount: float, minimum: float = 0.0) -> float:
    if Validators.too_many_decimals(amount):
        raise AmountPrecisionError()
    if amount < minimum or amount <= 0:
        raise AmountTooSmallError(minimum)
    return amount

def validate_address(address: str) -> str:
    if not Validators.is_valid_address(address):
        raise InvalidAddressError()
    return address
