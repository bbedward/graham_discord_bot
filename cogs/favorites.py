from discord.ext import commands
from discord.ext.commands import Bot, Context
from models.command import CommandInfo

import config
from util.discord.channel import ChannelUtil
from util.discord.messages import Messages
from util.env import Env
from db.models.favorite import Favorite
from db.models.user import User
from db.redis import RedisDB
from util.discord.paginator import Entry, Page, Paginator
from util.regex import RegexUtil, AmountAmbiguousException, AmountMissingException
from util.validators import Validators
from models.constants import Constants
from util.number import NumberUtil
from db.models.transaction import Transaction
from util.util import Utils
import asyncio
from tasks.transaction_queue import TransactionQueue

## Command documentation
ADD_FAVORITE_INFO = CommandInfo(
    triggers = ["addfavorite"],
    overview = "Add a user to your favorites list",
    details = f"Add a user to your favorites list. You can have up to **25 favorites**. Example: `{config.Config.instance().command_prefix}addfavorite @bbedward`"
)
REMOVE_FAVORITE_INFO = CommandInfo(
    triggers = ["unfavorite", "removefavorite"],
    overview = "Remove a user from your favorites list",
    details = f"Remove a user from your favorites list Example: `{config.Config.instance().command_prefix}removefavorite 419483863115366410`"
)
FAVORITES_INFO = CommandInfo(
    triggers = ["favorites"],
    overview = "View list of users you have favorited",
    details = f"View the list of every user you have favorited. You can tip all of them using `{config.Config.instance().command_prefix}{'banfavorites' if Env.banano() else 'ntipfavorites'} <amount>`"
)
TIPFAVORITES_INFO = CommandInfo(
    triggers = ["banfavorites" if Env.banano() else "ntipfavorites"],
    overview = "Tip all the favorites",
    details = f"Split a tip among all of the users in your favorites list - similar to a tipsplit. (**minimum tip is {Constants.TIP_MINIMUM} {Constants.TIP_UNIT}**)" +
                "\nExample: `{config.Config.instance().command_prefix}{'banfavorites' if Env.banano() else 'ntipfavorites'} <amount>`"
)

class FavoriteCog(commands.Cog):
    """Commands for admins only"""
    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx: Context):
        ctx.error = False
        msg = ctx.message
        # See if user exists in DB
        user = await User.get_user(msg.author)
        if user is None:
            ctx.error = True
            await Messages.send_error_dm(msg.author, f"You should create an account with me first, send me `{config.Config.instance().command_prefix}help` to get started.")
            return
        elif user.frozen:
            ctx.error = True
            await Messages.send_error_dm(msg.author, f"Your account is frozen. Contact an admin if you need further assistance.")
            return
        ctx.user = user
        # Update name if applicable
        await user.update_name(msg.author.name)

        # Special checks for tipfavorites
        if ctx.command.name == 'tipfavorites_cmd':
            # Check admins
            ctx.god = msg.author.id in config.Config.instance().get_admin_ids()
            ctx.admin = False
            author: discord.Member = msg.author
            for role in author.roles:
                if role.id in config.Config.instance().get_admin_roles():
                    ctx.admin = True
                    break
            # Check paused
            if await RedisDB.instance().is_paused():
                ctx.error = True
                await Messages.send_error_dm(msg.author, f"Transaction activity is currently suspended. I'll be back online soon!")
                return
            # See if amount meets tip_minimum requirement
            try:
                send_amount = RegexUtil.find_float(msg.content)
                if send_amount < Constants.TIP_MINIMUM:
                    raise AmountMissingException(f"Tip amount is too low, minimum is {Constants.TIP_MINIMUM}")
                elif Validators.too_many_decimals(send_amount):
                    await Messages.send_error_dm(ctx.message.author, f"You are only allowed to use {Env.precision_digits()} digits after the decimal.")
                    ctx.error = True
                    return
            except AmountMissingException:
                ctx.error = True

                await Messages.send_usage_dm(msg.author, TIPFAVORITES_INFO)
            ctx.send_amount = send_amount

    @commands.command(aliases=ADD_FAVORITE_INFO.triggers)
    async def addfavorite_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user

        to_add = []
        for u in msg.mentions:
            to_add.append(u)
        for u in msg.content.split():
            try:
                u_id = int(u.strip())
                if u_id == msg.author.id:
                    continue
                else:
                    for added in to_add:
                        if added.id == u_id:
                            continue
                discord_user = self.bot.get_user(u_id)
                if discord_user is not None:
                    to_add.append(discord_user)
            except Exception:
                pass

        if len(to_add) < 1:
            await Messages.send_usage_dm(msg.author, ADD_FAVORITE_INFO)
            return

        fav_count = await Favorite.filter(user=ctx.user).count()
        if (fav_count + len(to_add)) > 25:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"You can only have up to **25 favorites**. With this, you would have **{fav_count + len(to_add)}**.")
            return

        # Mute users
        added_count = 0
        for u in to_add:
            try:
                target_user = await User.get_user(u)
                if target_user is not None:
                    await Favorite.add_favorite(user, target_user)
                    added_count += 1
            except Exception:
                pass

        if added_count < 1:
            await Messages.send_error_dm(msg.author, "I was unable to favorite any users you mentioned.")
            return

        await msg.add_reaction("\u2764")
        await Messages.send_success_dm(msg.author, f"Successfully added {added_count} user(s) to your favorites")

    @commands.command(aliases=REMOVE_FAVORITE_INFO.triggers)
    async def removefavorite_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user

        to_remove = []
        for u in msg.mentions:
            to_remove.append(u)
        for u in msg.content.split():
            try:
                u_id = int(u.strip())
                if u_id == msg.author.id:
                    continue
                else:
                    for added in to_remove:
                        if added.id == u_id:
                            continue
                discord_user = self.bot.get_user(u_id)
                if discord_user is not None:
                    to_remove.append(discord_user)
            except Exception:
                pass

        if len(to_remove) < 1:
            await Messages.send_usage_dm(msg.author, REMOVE_FAVORITE_INFO)
            return

        # Mute users
        removed_count = 0
        for u in to_remove:
            try:
                target_user = await User.get_user(u)
                if target_user is not None:
                    await Favorite.delete_favorite(user, target_user)
                    removed_count += 1
            except Exception:
                pass

        if removed_count < 1:
            await Messages.send_error_dm(msg.author, "I was unable to remove any users you mentioned from your favorites.")
            return

        await msg.add_reaction("\U0001F494")
        await Messages.send_success_dm(msg.author, f"Successfully removed {removed_count} user(s) from your favorites")

    @commands.command(aliases=FAVORITES_INFO.triggers)
    async def favorites_cmd(self, ctx: Context):
        if ctx.error:
            return

        msg = ctx.message
        user = ctx.user

        favorited_list = await Favorite.filter(user=ctx.user).prefetch_related('favorited_user').all()

        if len(favorited_list) < 1:
            await msg.author.send("You don't have any users in your favorites list.")
            return

        # Build user list
        entries = []
        for u in favorited_list:
            entries.append(Entry(f"{u.favorited_user.name}", f"Remove with `{config.Config.instance().command_prefix}unfavorite {u.favorited_user.id}`"))

        # Build pages
        pages = []
        # Overview
        author=f"Your Favorites"
        description = f"Use `{config.Config.instance().command_prefix}unfavorite <user_id>` to remove a user from your favorites"
        i = 0
        entry_subset = []
        for e in entries:
            entry_subset.append(e)
            if i == 14:
                pages.append(Page(entries=entry_subset, author=author, description=description))
                i = 0
                entry_subset = []
            else:
                i += 1
        if len(entry_subset) > 0:
            pages.append(Page(entries=entry_subset, author=author, description=description))
        # Add a bonus page
        entries = [Entry("Remove all favorites", "Copy and paste the command to remove everybody from your favorites list")]
        author=f"Remove everybody"
        description = f"```{config.Config.instance().command_prefix}unfavorite"
        for u in favorited_list:
            description += f" {u.favorited_user.id}"
        description += "```"
        pages.append(Page(entries=entries, author=author,description=description))        

        # Start pagination
        pages = Paginator(self.bot, message=msg, page_list=pages,as_dm=True)
        await pages.paginate(start_page=1)

    @commands.command(aliases=TIPFAVORITES_INFO.triggers)
    async def tipfavorites_cmd(self, ctx: Context):
        if ctx.error:
            await Messages.add_x_reaction(ctx.message)
            return

        msg = ctx.message
        user = ctx.user
        send_amount = ctx.send_amount

        # Check anti-spam
        if not ctx.god and await RedisDB.instance().exists(f"tipfavoritesspam{msg.author.id}"):
            await Messages.add_timer_reaction(msg)
            await Messages.send_basic_dm(msg.author, "You can only tipfavorites once every 5 minutes")
            return

        # Get their favorites
        favorites = await Favorite.filter(user=user).prefetch_related('favorited_user').all()
        if len(favorites) < 1:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, "You don't have any favorites, add some first.")
            return

        individual_send_amount = NumberUtil.truncate_digits(send_amount / len(favorites), max_digits=Env.precision_digits())
        if individual_send_amount < Constants.TIP_MINIMUM:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"Tip amount too small, each user needs to receive at least {Constants.TIP_MINIMUM}. With your tip they'd only be getting {individual_send_amount}")
            return

        # See how much they need to make this tip.
        amount_needed = individual_send_amount * len(favorites)
        available_balance = Env.raw_to_amount(await user.get_available_balance())
        if amount_needed > available_balance:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"Your balance isn't high enough to complete this tip. You have **{available_balance} {Env.currency_symbol()}**, but this tip would cost you **{amount_needed} {Env.currency_symbol()}**")
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
                            member=self.bot.get_user(u.favorited_user.id),
                            message=f"You were tipped **{individual_send_amount} {Env.currency_symbol()}** by {msg.author.name.replace('`', '')}.\nUse `{config.Config.instance().command_prefix}mute {msg.author.id}` to disable notifications for this user."
                        )
                    )
        if len(tx_list) < 1:
            await Messages.add_x_reaction(msg)
            await Messages.send_error_dm(msg.author, f"No users you mentioned are eligible to receive tips.")
            return
        # Send DMs
        asyncio.ensure_future(Utils.run_task_list(task_list))
        # Add reactions
        await Messages.add_tip_reaction(msg, amount_needed)
        # Queue the actual sends
        for tx in tx_list:
            await TransactionQueue.instance().put(tx)
        # anti spam
        await RedisDB.instance().set(f"tipfavoritesspam{msg.author.id}", "as", expires=300)
        # Update stats
        stats: Stats = await user.get_stats(server_id=msg.guild.id)
        if msg.channel.id not in config.Config.instance().get_no_stats_channels():
            await stats.update_tip_stats(amount_needed)