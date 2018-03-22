import discord
from discord.ext import commands
from discord.ext.commands import Bot
import threading
from threading import Thread
import time
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

BOT_VERSION = "0.3"

# Change command prefix to whatever you want to begin commands with
client = Bot(command_prefix='!')
# Use custom help command
client.remove_command('help')

### Response Templates ###
COMMAND_NOT_FOUND_TEXT="I didn't understand that, try !help"
HELP_TEXT=	"""BananoTipBot v%s - An open source tip bot for Discord\n
		Developed by <@303599885800964097> - feel free to contribute and provide feedback \n
		\n
	```Supported commands are:
		\n
		!help - Show this message.
		!balance - Check the balance of your tip account.
		!deposit - Gives you your tip bot address (with QR code).
		!register - If you do not already have an account, one will be created.
		!ban 1000 @username - Tip user.
		!withdraw <address> - Withdraw all of your coins to your wallet.
		!ballers - Show who has tipped the most. \n\n\n
		NANO Tip Bot is open source: https://github.com/bbedward/NANO-Tip-Bot```"""
BALANCE_TEXT="```Actual Balance: %d Banano\nAvailable balance: %d Banano\nPending send: %d Banano\nPending receipt: %d Banano```"
DEPOSIT_TEXT="Your wallet address is %s. \n QR: %s"
AMOUNT_NOT_FOUND_TEXT="I couldn't find the amount in your message!"
INSUFFICIENT_FUNDS_TEXT="Insufficient Banano!"
TIP_ERROR_TEXT="**Error:** Beep bop boop beep beep beep @ChocolateFudCake."
TIP_RECEIVED_TEXT="You were tipped %d Banano by <@%s>"
WITHDRAW_SUCCESS_TEXT="Success!\nTXID: https://vault.banano.co.in/transaction/%s"
WITHDRAW_NO_BALANCE_TEXT="You have no Banano to withdraw"
WITHDRAW_ADDRESS_NOT_FOUND_TEXT="Withdraw address is required, try !help"
WITHDRAW_INVALID_ADDRESS_TEXT="Withdraw address is not valid"
WITHDRAW_ERROR_TEXT="**Error:** Beep bop boop beep beep beep @ChocolateFudCake. "
TOP_HEADER_TEXT="Big Tippers"
TOP_HEADER_EMPTY_TEXT="The leaderboard is empty!"
### END Response Templates ###

# Thread to process send transactions
class SendProcessor(Thread):
	def __init__(self):
		super(SendProcessor, self).__init__()
		self._stop_event = threading.Event()

	def run(self):
		while True:
			txs = db.get_unprocessed_transactions()
			for tx in txs:
				if self.stopped():
					break
				src_addr = tx['source_address']
				to_addr = tx['to_address']
				amount = int(tx['amount'])
				uid = tx['uid']
				raw_withdraw_amt = str(amount) + '00000000000000000000000000000'
				wallet_command = {
					'action': 'send',
					'wallet': settings.wallet,
					'source': src_addr,
					'destination': to_addr,
					'amount': int(raw_withdraw_amt),
					'id': uid
				}
				wallet_output = wallet.communicate_wallet(wallet_command)
				db.mark_transaction_processed(uid)
				logger.info('TX processed. UID: %s, TXID: https://vault.banano.co.in/transaction/%s', uid, wallet_output['block'])
				src_usr = db.get_user_by_wallet_address(src_addr)
				trg_usr = db.get_user_by_wallet_address(to_addr)
				if src_usr is not None:
					db.update_pending(src_usr.user_id, amount * -1, 0)
				if trg_usr is not None:
					db.update_pending(trg_usr.user_id, 0, amount * -1)
			if self.stopped():
				break
			time.sleep(10)

	def stop(self):
		self._stop_event.set()

	def stopped(self):
		return self._stop_event.is_set()

# Start bot, print info
@client.event
async def on_ready():
	logger.info("BANANO Tip Bot v%s started", BOT_VERSION)
	logger.info("Discord.py API version %s", discord.__version__)
	logger.info("Name: %s", client.user.name)
	logger.info("ID: %s", client.user.id)
	logger.info("Starting TX Processor Thread")
	try:
		SendProcessor().start()
	except (KeyboardInterrupt, SystemExit):
		SendProcessor().stop()

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
		user = db.get_user_by_id(ctx.message.author.id)
		actual_balance = wallet.get_balance(user, ctx.message.author.id)
		available_balance = actual_balance - user.pending_send
		await post_response(ctx.message, BALANCE_TEXT, actual_balance,available_balance,user.pending_send,user.pending_receive)

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
			amount = wallet.get_balance_adj(ctx.message.author.id)
			if amount == 0:
				await post_response(ctx.message, WITHDRAW_NO_BALANCE_TEXT);
			else:
				db.update_pending(ctx.message.author.id, amount, 0)
				uid = str(uuid.uuid4())
				wallet.make_transaction_to_address(source_address, amount, withdraw_address, uid)
				await post_response(ctx.message, WITHDRAW_SUCCESS_TEXT)
		except util.TipBotException as e:
			if e.error_type == "address_not_found":
				await post_response(ctx.message, WITHDRAW_ADDRESS_NOT_FOUND_TEXT)
			if e.error_type == "invalid_address":
				db.update_pending(ctx.message.author.id, amount * -1, 0)
				await post_response(ctx.message, WITHDRAW_INVALID_ADDRESS_TEXT)
			if e.error_type == "error":
				await post_response(ctx.message, WITHDRAW_ERROR_TEXT)

@client.command(pass_context=True)
async def ban(ctx):
	if ctx.message.channel.is_private:
		return

	try:
		amount = find_amount(ctx.message.content)
		# Make sure user has specified at least 1 recipient
		if len(ctx.message.mentions) < 1:
			return
		# Make sure this user has enough in their balance to complete this tip
		required_amt = amount * len(ctx.message.mentions)
		user_balance = wallet.get_balance_adj(ctx.message.author.id)
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

@client.command(pass_context=True, aliases=['ballers'])
async def bigtippers(ctx):
	top_users = wallet.get_top_users()
	if len(top_users) == 0:
		await post_response(ctx.message, TOP_HEADER_EMPTY_TEXT)
	else:
		response = TOP_HEADER_TEXT + "\n"
		for top_user in top_users:
			response += '```\n %d: %s - tipped %.0f BANANO```' % (top_user['index'],
					     top_user['name'], top_user['amount'])
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
		await client.add_reaction(message, '\:tip:425878628119871488') # TIP
	if amount > 0 and amount < 100:
		await client.add_reaction(message, '\:tick:425880814266351626') # S
	elif amount >= 100 and amount < 500:
		await client.add_reaction(message, '\:tick:425880814266351626') # C
		await client.add_reaction(message, '\:tick:425880814266351626') # R
	elif amount >= 500 and amount < 1000:
		await client.add_reaction(message, '\:tick:425880814266351626') # W
		await client.add_reaction(message, '\:tick:425880814266351626') # A
		await client.add_reaction(message, '\:tick:425880814266351626') # L
	elif amount >= 1000 and amount < 5000:
		await client.add_reaction(message, '\:tick:425880814266351626') # S
		await client.add_reaction(message, '\:tick:425880814266351626') # H
		await client.add_reaction(message, '\:tick:425880814266351626') # A
		await client.add_reaction(message, '\:tick:425880814266351626') # R
	elif amount >= 5000:
		await client.add_reaction(message, '\:tick:425880814266351626') # M
		await client.add_reaction(message, '\:tick:425880814266351626') # E
		await client.add_reaction(message, '\:tick:425880814266351626') # G
		await client.add_reaction(message, '\:tick:425880814266351626') # A
		await client.add_reaction(message, '\:tick:425880814266351626') # L

# Start the bot
client.run(settings.discord_bot_token)
