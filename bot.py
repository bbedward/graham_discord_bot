import discord
from discord.ext import commands
from discord.ext.commands import Bot
import collections
import random
import re
import errno
import asyncio
import uuid

import wallet
import util
import settings
import db

logger = util.get_logger("main")

BOT_VERSION = "0.2"

# Change command prefix to whatever you want to begin commands with
client = Bot(command_prefix='!')
# Use custom help command
client.remove_command('help')

### Response Templates ###
COMMAND_NOT_FOUND_TEXT="I didn't understand that, try !help"
HELP_TEXT=	"""NanoTipBot v%s - An open source NANO tip bot for Discord\n
		Developed by <@303599885800964097> - feel free to contribute and provide feedback \n
		\n
		Supported commands are: 
		\n
		:small_blue_diamond: !help or !man \n\n
		    Show this message.\n 
		\n
		:small_blue_diamond: !balance \n\n
		    Check the balance of your tip account \n
		\n
		:small_blue_diamond: !deposit or !register \n\n
		    Gives you your tip bot address (with QR code) \n
		    If you do not already have an account, one will be created \n
		\n
		:small_blue_diamond: !tip \n
		:small_blue_diamond: needs: amount who \n
		:small_blue_diamond: ex: !tip 1000 @bbedward\n\n
		    Tip other users. You have to mention who you want to tip and tell me the amount. 
		    If the operation is successful, the other users will be informed of your action. \n
		    Note that tip units are in 1/1000000th of a nano. \n
		    e.g. 1nano = 0.000001 NANO. \n
		\n
		:small_blue_diamond: !withdraw \n
		:small_blue_diamond: needs: address \n\n
		    Withdraw all of your coins to your wallet. You have to supply an 
		address for this. \n
		\n
		:small_blue_diamond: !bigtippers or !leaderboard \n\n
		    Show who has tipped the most. \n\n\n
		NANO Tip Bot is open source: https://github.com/bbedward/NANO-Tip-Bot"""
BALANCE_TEXT="Balance: %d nano"
DEPOSIT_TEXT="Your wallet address is %s. \n QR: %s"
AMOUNT_NOT_FOUND_TEXT="I couldn't find the amount in your message!"
INSUFFICIENT_FUNDS_TEXT="You don't have enough nano to tip that much!"
TIP_ERROR_TEXT="Something went wrong with the tip. I wrote to logs."
TIP_RECEIVED_TEXT="You were tipped %d nano by <@%s>"
WITHDRAW_SUCCESS_TEXT="Success!\nTXID: %s"
WITHDRAW_NO_BALANCE_TEXT="You have no nano to withdraw"
WITHDRAW_ADDRESS_NOT_FOUND_TEXT="Withdraw address is required, try !help"
WITHDRAW_INVALID_ADDRESS_TEXT="Withdraw address is not valid"
WITHDRAW_ERROR_TEXT="Something went wrong ! :thermometer_face: "
TOP_HEADER_TEXT="Big Tippers"
TOP_HEADER_EMPTY_TEXT="The leaderboard is empty!"
### END Response Templates ###

# Start bot, print info
@client.event
async def on_ready():
	logger.info("NANO Tip Bot v%s started", BOT_VERSION)
	logger.info("Discord.py API version %s", discord.__version__)
	logger.info("Name: %s", client.user.name)
	logger.info("ID: %s", client.user.id)

# Override on_message and do our spam check here
@client.event
async def on_message(message):
	if db.last_msg_check(message.author.id) == False:
		return
	await client.process_commands(message)

### Commands
@client.command(pass_context=True, aliases=['man'])
async def help(ctx):
	if ctx.message.channel.is_private:
		await post_response(ctx.message, HELP_TEXT, BOT_VERSION)

@client.command(pass_context=True)
async def balance(ctx):
	if ctx.message.channel.is_private:
		balance = wallet.get_balance(ctx.message.author.id)
		await post_response(ctx.message, BALANCE_TEXT, balance)

@client.command(pass_context=True, aliases=['register'])
async def deposit(ctx):
	if ctx.message.channel.is_private:
		user_deposit_address = wallet.create_or_fetch_user(ctx.message.author.id, ctx.message.author.name).wallet_address
		await post_response(ctx.message, DEPOSIT_TEXT, user_deposit_address,
			      get_qr_url(user_deposit_address))

@client.command(pass_context=True)
async def withdraw(ctx):
	if ctx.message.channel.is_private:
		try:
			withdraw_address = find_address(ctx.message.content)
			source_address = wallet.get_address(ctx.message.author.id)
			amount = wallet.get_balance(ctx.message.author.id)
			if amount == 0:
				await post_response(ctx.message, WITHDRAW_NO_BALANCE_TEXT);
			else:
				uid = str(uuid.uuid4())
				txid = wallet.make_transaction_to_address(source_address, amount, withdraw_address, uid)
				await post_response(ctx.message, WITHDRAW_SUCCESS_TEXT, txid)
		except util.TipBotException as e:
			if e.error_type == "address_not_found":
				await post_response(ctx.message, WITHDRAW_ADDRESS_NOT_FOUND_TEXT)
			if e.error_type == "invalid_address":
				await post_response(ctx.message, WITHDRAW_INVALID_ADDRESS_TEXT)
			if e.error_type == "error":
				await post_response(ctx.message, WITHDRAW_ERROR_TEXT)

@client.command(pass_context=True)
async def tip(ctx):
	if ctx.message.channel.is_private:
		return

	try:
		amount = find_amount(ctx.message.content)
		# Make sure user has specified at least 1 recipient
		if len(ctx.message.mentions) < 1:
			return
		# Make sure this user has enough in their balance to complete this tip
		required_amt = amount * len(ctx.message.mentions)
		user_balance = wallet.get_balance(ctx.message.author.id)
		if user_balance < required_amt:
			await post_dm(ctx.message.author, INSUFFICIENT_FUNDS_TEXT)
			return
		# Distribute tips
		for member in ctx.message.mentions:
			# Don't allow user to tip themselves, or people in exempt users list
			# We do it this way because there may be multiple recipients on 1 tip
			# So we just ignore the invalid ones, basically
			if member.id in settings.exempt_users:
				required_amt-=amount
			elif member.id == ctx.message.author.id:
				required_amt-=amount
			else:
				uid = str(uuid.uuid4())
				wallet.make_transaction_to_user(ctx.message.author.id, amount, member.id, member.name, uid)
				await post_dm(member, TIP_RECEIVED_TEXT, amount, ctx.message.author.id)
		# Post message reactions
		await react_to_message(ctx.message, required_amt)
	except util.TipBotException as e:
		if e.error_type == "amount_not_found":
			await post_dm(ctx.message.author, AMOUNT_NOT_FOUND_TEXT)
		if e.error_type == "error":
			await post_response(ctx.message, TIP_ERROR_TEXT)

@client.command(pass_context=True, aliases=['leaderboard'])
async def bigtippers(ctx):
	top_users = wallet.get_top_users()
	if len(top_users) == 0:
		await post_response(ctx.message, TOP_HEADER_EMPTY_TEXT)
	else:
		response = TOP_HEADER_TEXT + "\n"
		for top_user in top_users:
			response += '\n %d: %.6f NANO tipped by %s' % (top_user['index'],
					     top_user['amount'], top_user['name'])
		await post_response(ctx.message, response)

### Utility Functions
def get_qr_url(text):
	return 'https://chart.googleapis.com/chart?cht=qr&chl=%s&chs=180x180&choe=UTF-8&chld=L|2' % text

def find_address(input_text):
	address = input_text.split(' ')
	if len(address) == 1:
		raise util.TipBotException("invalid_address")
	elif address[1] is None:
		raise util.TipBotException("invalid_address")
	return address[1]

def find_amount(input_text):
	regex = r'(?:^|\s)(\d*\.?\d+)(?=$|\s)'
	matches = re.findall(regex, input_text, re.IGNORECASE)
	if len(matches) == 1:
		return float(matches[0].strip())
	else:
		raise util.TipBotException("amount_not_found")

### Re-Used Discord Functions
async def post_response(message, template, *args):
	response = template % tuple(args)
	if not message.channel.is_private:
		response = "<@" + message.author.id + "> " + response
	logger.info("sending response: '%s' to message: %s", response, message.content)
	await client.send_message(message.channel, response)


async def post_dm(member, template, *args):
	response = template % tuple(args)
	logger.info("sending dm: '%s' to user: %s", response, member.id)
	await client.send_message(member, response)

async def react_to_message(message, amount):
	if amount > 0:
		await client.add_reaction(message, '\U00002611')   # check mark
	if amount > 0 and amount < 1000:
		await client.add_reaction(message, '\U0001F1F8') # S
		await client.add_reaction(message, '\U0001F1ED') # H
		await client.add_reaction(message, '\U0001F1F7') # R
		await client.add_reaction(message, '\U0001F1EE') # I 
		await client.add_reaction(message, '\U0001F1F2') # M
		await client.add_reaction(message, '\U0001F1F5') # P
	elif amount >= 1000 and amount < 10000:
		await client.add_reaction(message, '\U0001F1E8') # C
		await client.add_reaction(message, '\U0001F1F7') # R
		await client.add_reaction(message, '\U0001F1E6') # A
		await client.add_reaction(message, '\U0001F1E7') # B
	elif amount >= 10000 and amount < 100000:
		await client.add_reaction(message, '\U0001F1FC') # W
		await client.add_reaction(message, '\U0001F1E6') # A
		await client.add_reaction(message, '\U0001F1F1') # L
		await client.add_reaction(message, '\U0001F1F7') # R
		await client.add_reaction(message, '\U0001F1FA') # U
		await client.add_reaction(message, '\U0001F1F8') # S
	elif amount >= 100000 and amount < 1000000:
		await client.add_reaction(message, '\U0001F1F8') # S
		await client.add_reaction(message, '\U0001F1ED') # H
		await client.add_reaction(message, '\U0001F1E6') # A
		await client.add_reaction(message, '\U0001F1F7') # R
		await client.add_reaction(message, '\U0001F1F0') # K
	elif amount >= 1000000:
		await client.add_reaction(message, '\U0001F1F2') # M
		await client.add_reaction(message, '\U0001F1EA') # E
		await client.add_reaction(message, '\U0001F1EC') # G
		await client.add_reaction(message, '\U0001F1E6') # A
		await client.add_reaction(message, '\U0001F1F1') # L
		await client.add_reaction(message, '\U0001F1E9') # D
		await client.add_reaction(message, '\U0001F1F4') # O
		await client.add_reaction(message, '\U0001F1F3') # N

# Start the bot
client.run(settings.discord_bot_token)

