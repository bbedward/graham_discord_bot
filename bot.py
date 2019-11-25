from cogs import account, help, tips
from config import Config
from discord.ext.commands import Bot
from db.models.transaction import Transaction
from db.tortoise_config import init_db
from util.env import Env
from util.logger import setup_logger
from version import __version__

import asyncio
import discord
import logging
from rpc.client import RPCClient
from process.transaction_queue import TransactionQueue

# Configuration
config = Config.instance()

# Setup logger
setup_logger(config.log_file, log_level=logging.DEBUG if config.debug else logging.INFO)
logger = logging.getLogger()

client = Bot(command_prefix=config.command_prefix)
client.remove_command('help')

# Install uvloop
try:
	import uvloop
	uvloop.install()
except ImportError:
	logger.warn("Couldn't install uvloop, falling back to the slower asyncio event loop")

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
	logger.info(f"Re-queueing any unprocessed transactions")
	unprocessed_txs = await Transaction.filter(block_hash=None).all()
	for tx in unprocessed_txs:
		await TransactionQueue.instance().put(tx)
	logger.info(f"Re-queued {len(unprocessed_txs)} transactions")

@client.event
async def on_message(message):
	# disregard messages sent by the bot
	if message.author.id == client.user.id:
		return
    # Process commands
	await client.process_commands(message)

if __name__ == "__main__":
	# Add cogs
	client.add_cog(account.Account(client))
	client.add_cog(tips.Tips(client))
	client.add_cog(help.Help(client, config.command_prefix))
	# Start bot
	loop = asyncio.get_event_loop()
	try:
		tasks = [
			client.start(config.bot_token),
			# Create two queue consumers for transactions
			TransactionQueue.instance().queue_consumer(),
			TransactionQueue.instance().queue_consumer()
		]
		loop.run_until_complete(asyncio.wait(tasks))
	except:
		logger.info("Graham is exiting")
	finally:
		loop.run_until_complete(client.logout())
		loop.run_until_complete(RPCClient.instance().close())
		loop.close()
