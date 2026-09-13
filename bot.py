try:
	import uvloop
	uvloop.install()
except ImportError:
	print("Couldn't install uvloop, falling back to the slower asyncio event loop")

import asyncio
import logging
import os
import sys

import discord
import rapidjson as json
from discord import app_commands
from discord.ext import commands
from tortoise import run_async

from cogs import account, help, tips, stats, rain, admin, useroptions, favorites, spy, giveaway
from config import Config
from db.models.transaction import Transaction
from db.redis import RedisDB
from db.tortoise_config import DBConfig
from rpc.client import RPCClient
from server import GrahamServer
from tasks.transaction_queue import TransactionQueue
from util.discord.messages import Messages
from util.env import Env
from util.logger import setup_logger
from version import __version__

config = Config.instance()

# Unique ID for redis subscriptions
subID = f"{config.bot_token}:deposits"

setup_logger(config.log_file, log_level=logging.DEBUG if config.debug else logging.INFO)
logger = logging.getLogger()

# Application flag bits: full flags are granted by intent review, LIMITED
# variants let unverified bots (<100 servers) use the intent when the portal
# toggle is on. https://discord.com/developers/docs/resources/application
GATEWAY_PRESENCE = 1 << 12 | 1 << 13
GATEWAY_GUILD_MEMBERS = 1 << 14 | 1 << 15

async def fetch_application_flags() -> int | None:
	import aiohttp
	try:
		async with aiohttp.ClientSession() as session:
			async with session.get('https://discord.com/api/v10/applications/@me', headers={'Authorization': f'Bot {config.bot_token}'}) as resp:
				if resp.status != 200:
					return None
				data = await resp.json()
				return data.get('flags', 0)
	except Exception:
		return None

async def build_intents() -> discord.Intents:
	intents = discord.Intents.default()
	match os.getenv('GRAHAM_PRIVILEGED_INTENTS', '').lower():
		case '1' | 'true':
			intents.members = True
			intents.presences = True
			return intents
		case '0' | 'false':
			logger.warning("GRAHAM_PRIVILEGED_INTENTS=0 - running without Members/Presence intents")
			return intents
	flags = await fetch_application_flags()
	if flags is None:
		# Probe failed - assume they're granted, matching pre-fallback behavior
		intents.members = True
		intents.presences = True
		return intents
	intents.members = bool(flags & GATEWAY_GUILD_MEMBERS)
	intents.presences = bool(flags & GATEWAY_PRESENCE)
	if not intents.members:
		logger.warning("Members intent not enabled for this application - member lookups fall back to HTTP fetches and rains may be slower")
	if not intents.presences:
		logger.warning("Presence intent not enabled for this application - DND users will receive tip notification DMs")
	return intents

class GrahamTree(app_commands.CommandTree):
	async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
		if isinstance(error, app_commands.CheckFailure):
			await Messages.respond_error(interaction, str(error))
			return
		logger.exception("Unhandled app command error", exc_info=error)
		await Messages.respond_error(interaction, "Something went wrong, try again later.")

class GrahamBot(commands.Bot):
	def __init__(self, intents: discord.Intents):
		super().__init__(command_prefix=commands.when_mentioned, intents=intents, tree_cls=GrahamTree)
		self.guild_sync_done = False

	async def setup_hook(self):
		await self.add_cog(account.AccountCog(self))
		await self.add_cog(tips.TipsCog(self))
		await self.add_cog(help.HelpCog(self))
		await self.add_cog(stats.StatsCog(self))
		await self.add_cog(rain.RainCog(self))
		await self.add_cog(admin.AdminCog(self))
		await self.add_cog(useroptions.UserOptionsCog(self))
		await self.add_cog(favorites.FavoriteCog(self))
		await self.add_cog(spy.SpyCog(self))
		await self.add_cog(giveaway.GiveawayCog(self))
		asyncio.create_task(TransactionQueue.instance(bot=self).queue_consumer())
		asyncio.create_task(requeue_transactions_periodically(self))
		asyncio.create_task(deposit_notification_sub(self))
		await self.tree.sync()

	async def on_ready(self):
		logger.info(f"Starting Graham v{__version__}")
		logger.info(f"Discord.py version {discord.__version__}")
		logger.info(f"Bot name: {self.user.name}")
		logger.info(f"Bot Discord ID: {self.user.id}")
		logger.info(f"Members intent: {self.intents.members}, Presence intent: {self.intents.presences}")
		await self.change_presence(activity=discord.Game(config.playing_status))

		logger.info(f"Re-queueing any unprocessed transactions")
		await requeue_transactions(self)

		# Global commands can take up to an hour to propagate, guild copies are instant
		if not self.guild_sync_done:
			self.guild_sync_done = True
			for guild in self.guilds:
				self.tree.copy_global_to(guild=guild)
				await self.tree.sync(guild=guild)
			logger.info(f"Synced commands to {len(self.guilds)} guilds")

async def requeue_transactions(client: commands.Bot):
	unprocessed_txs = await Transaction.filter(block_hash=None, destination__not_isnull=True, failed=False).all().prefetch_related('sending_user', 'receiving_user')
	for tx in unprocessed_txs:
		await TransactionQueue.instance(bot=client).put(tx)
	logger.info(f"Re-queued {len(unprocessed_txs)} transactions")

async def requeue_transactions_periodically(client: commands.Bot):
	while True:
		await asyncio.sleep(600)
		await requeue_transactions(client)

async def deposit_notification_sub(client: commands.Bot):
	pubsub = await RedisDB.instance().pubsub()
	await pubsub.subscribe(subID)
	async for message in pubsub.listen():
		if message['type'] != 'message':
			continue
		try:
			msg = json.loads(message['data'])
			discord_user = await client.fetch_user(msg["id"])
			await Messages.send_success_dm(discord_user, msg["message"], header="Deposit Success", footer=f"I only notify you of deposits that are {10 if Env.banano() else 0.1} {Env.currency_symbol()} or greater.")
		except discord.NotFound:
			continue
		except Exception:
			logger.exception("Error handling deposit notification")

async def start_bot():
	client = None
	try:
		logger.info("Initializing database")
		await DBConfig().init_db()
		client = GrahamBot(await build_intents())
		await client.start(config.bot_token)
	except discord.PrivilegedIntentsRequired:
		logger.error("Discord refused the Members/Presence intents even though the application flags advertised them. Untick the removed intents in the Developer Portal, or force unprivileged mode with GRAHAM_PRIVILEGED_INTENTS=0.")
	except Exception:
		logger.exception("Graham exited with exception")
	except BaseException:
		pass
	finally:
		logger.info("Graham is exiting")
		if client is not None:
			await client.close()
		await RPCClient.close()
		await RedisDB.close()

def start_server():
		server_host, server_port = Config.instance().get_server_info()
		if server_host is None or server_port is None:
			logger.info("Graham server is disabled")
			sys.exit(1)
		server = GrahamServer(subID, server_host, server_port)
		logger.info(f"Graham server running at {server_host}:{server_port}")
		DBConfig().init_db_aiohttp(server.app)
		server.start()

if __name__ == "__main__":
	match sys.argv[1] if len(sys.argv) > 1 else None:
		case 'start_bot':
			run_async(start_bot())
		case 'start_server':
			start_server()
		case _:
			print(f"Usage: python3 {sys.argv[0]} <start_bot|start_server>")
			sys.exit(1)
