from cogs import tips
from discord.ext.commands import Bot
from db.tortoise_config import init_db
from util.env import Env
from util.logger import get_logger
from . import __version__

import argparse
import discord
import logging
import sys

parser = argparse.ArgumentParser(description=f"Graham NANO/BANANO TipBot v{__version__}")
parser.add_argument('-p', '--prefix', type=str, help='Command prefix for bot commands', default='!')
parser.add_argument('-l', '--log-file', type=str, help='Log file location', default='/tmp/graham_tipbot.log')
parser.add_argument('-s', '--status', type=str, help="The bot's 'playing status'", default=None, required=False)
parser.add_argument('-t', '--token', type=str, help='Discord bot token', required=True)
parser.add_argument('--debug', action='store_true', help='Runs in debug mode if specified', default=False)
options = parser.parse_args()

# Parse options
COMMAND_PREFIX = options.prefix
if len(COMMAND_PREFIX) != 1:
    print("Command prefix can only be 1 character")
    sys.exit(1)
LOG_FILE = options.log_file
DEBUG = options.debug
PLAYING_STATUS = f"{COMMAND_PREFIX}help for help" if options.status is None else options.status
BOT_TOKEN = options.token

# Setup logger
logger = get_logger(LOG_FILE, log_level=logging.DEBUG if DEBUG else logging.INFO)

client = Bot(command_prefix=COMMAND_PREFIX)
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
	await client.change_presence(activity=discord.Game(PLAYING_STATUS))

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
	# Start bot
	client.run(BOT_TOKEN)