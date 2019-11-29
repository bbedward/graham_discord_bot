# Install uvloop
try:
	import uvloop
	uvloop.install()
except ImportError:
	print("Couldn't install uvloop, falling back to the slower asyncio event loop")

from cogs import account, help, tips, tip_legacy, stats, rain
from config import Config
from discord.ext.commands import Bot
from db.models.transaction import Transaction
from db.tortoise_config import init_db
from db.redis import RedisDB
from server import GrahamServer
from util.discord.channel import ChannelUtil
from util.env import Env
from util.logger import setup_logger
from version import __version__

import asyncio
import discord
import logging
from rpc.client import RPCClient
from tasks.transaction_queue import TransactionQueue

# Configuration
config = Config.instance()

# Setup logger
setup_logger(config.log_file, log_level=logging.DEBUG if config.debug else logging.INFO)
logger = logging.getLogger()

client = Bot(command_prefix=config.command_prefix)
client.remove_command('help')

### Bot events

@client.event
async def on_ready():
	logger.info("Initializing database")
	await init_db()
	logger.info(f"Starting Graham v{__version__}")
	logger.info(f"Discord.py version {discord.__version__}")
	logger.info(f"Bot name: {client.user.name}")
	logger.info(f"Bot Discord ID: {client.user.id}")
	await client.change_presence(activity=discord.Game(config.playing_status))

	# Process any transactions in our DB that are outstanding
	logger.info(f"Re-queueing any unprocessed transactions")
	unprocessed_txs = await Transaction.filter(block_hash=None).all().prefetch_related('sending_user', 'receiving_user')
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

if __name__ == "__main__":
	# Add cogs
	client.add_cog(account.Account(client))
	client.add_cog(tips.Tips(client))
	client.add_cog(help.Help(client))
	client.add_cog(stats.TipStats(client))
	client.add_cog(rain.Rain(client))
	if not Env.banano():
		# Add a command to warn users that tip unit has changed
		client.add_cog(tip_legacy.TipLegacy(client))
	# Start bot
	loop = asyncio.get_event_loop()
	try:
		tasks = [
			client.start(config.bot_token),
			# Create two queue consumers for transactions
			TransactionQueue.instance(bot=client).queue_consumer(),
			TransactionQueue.instance(bot=client).queue_consumer()
		]
		# Setup optional server if configured
		server_host, server_port = Config.instance().get_server_info()
		if server_host is None or server_port is None:
			logger.info("Graham server is disabled")
		else:
			server = GrahamServer(client, server_host, server_port)
			logger.info(f"Graham server running at {server_host}:{server_port}")
			tasks.append(server.start())
		loop.run_until_complete(asyncio.wait(tasks))
	except Exception:
		logger.exception("Graham exited with exception")
	except BaseException:
		pass
	finally:
		logger.info("Graham is exiting")
		tasks = [
			client.logout(),
			RPCClient.close(),
			RedisDB.close()
		]
		loop.run_until_complete(asyncio.wait(tasks))
		loop.close()
