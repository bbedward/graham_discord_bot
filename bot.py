from cogs import tips, help
from config import Config
from discord.ext.commands import Bot
from db.tortoise_config import init_db
from util.env import Env
from util.logger import setup_logger
from version import __version__

import discord
import ipaddress
import logging
import sys

# Configuration
config = Config()

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

@client.event
async def on_message(message):
	# disregard messages sent by the bot
	if message.author.id == client.user.id:
		return
    # Process commands
	await client.process_commands(message)

if __name__ == "__main__":
	# Add cogs
	client.add_cog(tips.Tips(client))
	client.add_cog(help.Help(client, config.command_prefix))
	# Start bot
	client.run(config.bot_token)