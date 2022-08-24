# Install uvloop
try:
	import uvloop
	uvloop.install()
except ImportError:
	print("Couldn't install uvloop, falling back to the slower asyncio event loop")

from cogs import account, help, tips, tip_legacy, stats, rain, admin, useroptions, favorites, spy, giveaway
from config import Config
from discord.ext.commands import Bot
from db.models.transaction import Transaction
from db.tortoise_config import DBConfig
from db.redis import RedisDB
from server import GrahamServer
from tortoise import Tortoise, run_async
from util.discord.channel import ChannelUtil
from util.env import Env
from util.logger import setup_logger
from version import __version__

import sys
import asyncio
import discord
intents = discord.Intents.default()
intents.members = True
intents.presences = True
import logging
from rpc.client import RPCClient
from tasks.transaction_queue import TransactionQueue

# Configuration
config = Config.instance()

# Setup logger
setup_logger(config.log_file, log_level=logging.DEBUG if config.debug else logging.INFO)
logger = logging.getLogger()

# TODO - re-enable for discord.py 1.5.0
client = Bot(command_prefix=config.command_prefix, intents=intents)
client.remove_command('help')

# Periodic re-queue tranasctions
async def reQueueTransactions(client):
	while True:
		logger.info(f"Re-queue task started")
		await asyncio.sleep(600)
		logger.info(f"Re-queue task running")
		TransactionQueue.instance(bot=client).clear()
		unprocessed_txs = await Transaction.filter(block_hash=None, destination__not_isnull=True).all().prefetch_related('sending_user', 'receiving_user')
		for tx in unprocessed_txs:
			await TransactionQueue.instance(bot=client).put(tx)
		logger.info(f"Re-queued {len(unprocessed_txs)} transactions")

### Bot events

@client.event
async def on_ready():
	logger.info(f"Starting Graham v{__version__}")
	logger.info(f"Discord.py version {discord.__version__}")
	logger.info(f"Bot name: {client.user.name}")
	logger.info(f"Bot Discord ID: {client.user.id}")
	await client.change_presence(activity=discord.Game(config.playing_status))

	# Process any transactions in our DB that are outstanding
	logger.info(f"Re-queueing any unprocessed transactions")
	unprocessed_txs = await Transaction.filter(block_hash=None, destination__not_isnull=True).all().prefetch_related('sending_user', 'receiving_user')
	for tx in unprocessed_txs:
		await TransactionQueue.instance(bot=client).put(tx)
	logger.info(f"Re-queued {len(unprocessed_txs)} transactions")

@client.event
async def on_message(message: discord.Message):
	# disregard messages sent by the bot
	if message.author.id == client.user.id:
		return
    # Process commands
	await client.process_commands(message)

async def start_bot():
	# Add cogs
	client.add_cog(account.AccountCog(client))
	client.add_cog(tips.TipsCog(client))
	client.add_cog(help.HelpCog(client))
	client.add_cog(stats.StatsCog(client))
	client.add_cog(rain.RainCog(client))
	client.add_cog(admin.AdminCog(client))
	client.add_cog(useroptions.UserOptionsCog(client))
	client.add_cog(favorites.FavoriteCog(client))
	client.add_cog(spy.SpyCog(client))
	client.add_cog(giveaway.GiveawayCog(client))
	if not Env.banano():
		# Add a command to warn users that tip unit has changed
		client.add_cog(tip_legacy.TipLegacyCog(client))
	# Start bot
	try:
		# Initialize database first
		logger.info("Initializing database")
		await DBConfig().init_db()
		asyncio.create_task(TransactionQueue.instance(bot=client).queue_consumer())
		asyncio.create_task(reQueueTransactions(client))
		await client.start(config.bot_token),
	except Exception:
		logger.exception("Graham exited with exception")
	except BaseException:
		pass
	finally:
		logger.info("Graham is exiting")
		await client.logout()
		await RPCClient.close()
		await RedisDB.close()

async def start_server():
		# Setup optional server if configured
		server_host, server_port = Config.instance().get_server_info()
		if server_host is None or server_port is None:
			logger.info("Graham server is disabled")
			sys.exit(1)
		server = GrahamServer(client, server_host, server_port)
		logger.info(f"Graham server running at {server_host}:{server_port}")
		DBConfig().init_db_aiohttp(server.app)
		await server.start()

if __name__ == "__main__":
	if len(sys.argv) < 2:
		print(f"Usage: python3 {sys.argv[0]} <start_bot|start_server>")
		sys.exit(1)
	elif sys.argv[1] not in ['start_bot', 'start_server']:
		print(f"Usage: python3 {sys.argv[0]} <start_bot|start_server>")
		sys.exit(1)

	if sys.argv[1] == 'start_bot':
		run_async(start_bot())
		
	# start server
	asyncio.run(start_server())