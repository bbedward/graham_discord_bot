import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import config
from db.models.favorite import Favorite
from db.models.stats import Stats
from db.models.transaction import Transaction
from db.models.user import User
from db.redis import RedisDB
from models.command import CommandInfo
from models.constants import Constants
from tasks.transaction_queue import TransactionQueue
from util.discord.messages import Messages
from util.discord.paginator import Entry, Page, Paginator
from util.discord.resolver import require_user, resolve, validate_amount
from util.discord.users import resolve_user
from util.env import Env
from util.util import Utils

## Command documentation
ADD_FAVORITE_INFO = CommandInfo(
    triggers = ["addfavorite"],
    overview = "Add a user to your favorites list",
    details = "Add a user to your favorites list. You can have up to **25 favorites**. Example: `/addfavorite @bbedward`"
)
REMOVE_FAVORITE_INFO = CommandInfo(
    triggers = ["unfavorite", "removefavorite"],
    overview = "Remove a user from your favorites list",
    details = "Remove a user from your favorites list, or all of them at once. Example: `/unfavorite @bbedward`"
)
FAVORITES_INFO = CommandInfo(
    triggers = ["favorites"],
    overview = "View list of users you have favorited",
    details = f"View the list of every user you have favorited. You can tip all of them using `/{'banfavorites' if Env.banano() else 'ntipfavorites'} <amount>`"
)
TIPFAVORITES_INFO = CommandInfo(
    triggers = ["banfavorites" if Env.banano() else "ntipfavorites"],
    overview = "Tip all the favorites",
    details = f"Split a tip among all of the users in your favorites list - similar to a tipsplit. (**minimum tip is {Constants.TIP_MINIMUM} {Constants.TIP_UNIT}**)" +
                f"\nExample: `/{'banfavorites' if Env.banano() else 'ntipfavorites'} <amount>`"
)

class FavoriteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="addfavorite", description=ADD_FAVORITE_INFO.overview)
    @app_commands.describe(user="The user to add to your favorites")
    async def addfavorite_cmd(self, interaction: discord.Interaction, user: discord.User):
        inv = await resolve(interaction, check_paused=False)
        if user.id == interaction.user.id:
            await Messages.respond_error(interaction, "You can't favorite yourself.")
            return

        fav_count = await Favorite.filter(user=inv.user).count()
        if fav_count + 1 > 25:
            await Messages.respond_error(interaction, "You can only have up to **25 favorites**.")
            return

        target_user = await User.get_user(user)
        if target_user is None:
            await Messages.respond_error(interaction, "That user doesn't have an account with me.")
            return
        await Favorite.add_favorite(inv.user, target_user)
        await Messages.respond_success(interaction, f"Successfully added {user.name} to your favorites ❤")

    @app_commands.command(name="unfavorite", description=REMOVE_FAVORITE_INFO.overview)
    @app_commands.describe(user="The user to remove from your favorites", everyone="Remove every user from your favorites list")
    async def removefavorite_cmd(self, interaction: discord.Interaction, user: discord.User = None, everyone: bool = False):
        inv = await resolve(interaction, check_paused=False)
        if user is None and not everyone:
            await Messages.respond_error(interaction, "Specify a user to remove, or set `everyone` to remove all favorites.")
            return

        if everyone:
            favorites = await Favorite.filter(user=inv.user).prefetch_related('favorited_user').all()
            for fav in favorites:
                await Favorite.delete_favorite(inv.user, fav.favorited_user)
            await Messages.respond_success(interaction, f"Successfully removed {len(favorites)} user(s) from your favorites \U0001F494")
            return

        target_user = await User.get_user(user)
        if target_user is None:
            await Messages.respond_error(interaction, "That user doesn't have an account with me.")
            return
        await Favorite.delete_favorite(inv.user, target_user)
        await Messages.respond_success(interaction, f"Successfully removed {user.name} from your favorites \U0001F494")

    @app_commands.command(name="favorites", description=FAVORITES_INFO.overview)
    async def favorites_cmd(self, interaction: discord.Interaction):
        inv = await resolve(interaction, check_paused=False)
        favorited_list = await Favorite.filter(user=inv.user).prefetch_related('favorited_user').all()
        if len(favorited_list) < 1:
            await Messages.respond_success(interaction, "You don't have any users in your favorites list.", header="Your Favorites")
            return

        entries = [Entry(f"{u.favorited_user.name}", f"Remove with `/unfavorite` and their ID: {u.favorited_user.id}") for u in favorited_list]
        author = "Your Favorites"
        description = "Use `/unfavorite` to remove a user from your favorites"
        pages = [Page(entries=entries[i:i + 15], author=author, description=description) for i in range(0, len(entries), 15)]
        await Paginator.send_as_response(interaction, pages, ephemeral=True)

    @app_commands.command(name="banfavorites" if Env.banano() else "ntipfavorites", description=TIPFAVORITES_INFO.overview)
    @app_commands.describe(amount="Amount to split between all of your favorites")
    @app_commands.guild_only()
    async def tipfavorites_cmd(self, interaction: discord.Interaction, amount: float):
        await interaction.response.defer()
        inv = await require_user(interaction)
        validate_amount(amount, minimum=Constants.TIP_MINIMUM)
        user = inv.user

        # Check anti-spam
        if not inv.god and await RedisDB.instance().exists(f"tipfavoritesspam{interaction.user.id}"):
            await Messages.respond_error(interaction, "You can only tipfavorites once every 5 minutes")
            return

        favorites = await Favorite.filter(user=user).prefetch_related('favorited_user').all()
        if len(favorites) < 1:
            await Messages.respond_error(interaction, "You don't have any favorites, add some first.")
            return

        individual_send_amount = Env.truncate_digits(amount / len(favorites), max_digits=Env.precision_digits())
        if individual_send_amount < Constants.TIP_MINIMUM:
            await Messages.respond_error(interaction, f"Tip amount too small, each user needs to receive at least {Constants.TIP_MINIMUM}. With your tip they'd only be getting {individual_send_amount}")
            return

        amount_needed = individual_send_amount * len(favorites)
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount_needed > available_balance:
            await Messages.respond_error(interaction, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount_needed} {Env.currency_symbol()}**")
            return

        # Make the transactions in the database
        tx_list = []
        task_list = []
        for u in favorites:
            tx = await Transaction.create_transaction_internal_dbuser(
                sending_user=user,
                amount=individual_send_amount,
                receiving_user=u.favorited_user
            )
            if tx is not None:
                tx_list.append(tx)
                if not await user.is_muted_by(u.favorited_user.id):
                    task_list.append(
                        Messages.send_basic_dm(
                            member=await resolve_user(self.bot, u.favorited_user.id),
                            message=f"You were tipped **{individual_send_amount} {Env.currency_symbol()}** by {interaction.user.name.replace('`', '')}.\nUse `/mute` to disable notifications for this user.",
                            skip_dnd=True
                        )
                    )
        if len(tx_list) < 1:
            await Messages.respond_error(interaction, "No users in your favorites are eligible to receive tips.")
            return
        # Queue the actual sends
        for tx in tx_list:
            await TransactionQueue.instance().put(tx)
        # Send DMs
        asyncio.ensure_future(Utils.run_task_list(task_list))
        targets = ', '.join(f"<@{u.favorited_user.id}>" for u in favorites)
        await Messages.send_tip_line(interaction, amount_needed, interaction.user, targets)
        # anti spam
        await RedisDB.instance().set(f"tipfavoritesspam{interaction.user.id}", "as", expires=300)
        # Update stats
        stats: Stats = await user.get_stats(server_id=interaction.guild_id)
        if interaction.channel_id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(amount_needed)
