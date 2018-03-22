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
import datetime

import wallet
import util
import settings
import db

logger = util.get_logger("main")

BOT_VERSION = "0.4"

# How many users to display in the top users count
TOP_TIPPERS_COUNT=15
# Minimum Amount for !rain
RAIN_MINIMUM = settings.rain_minimum
# Spam Threshold (Seconds) - how long to output certain commands (e.g. bigtippers0
SPAM_THRESHOLD=60
# Change command prefix to whatever you want to begin commands with
client = Bot(command_prefix='!')
# Use custom help command
client.remove_command('help')

# Spam prevention
last_big_tippers=datetime.datetime.now()

### Response Templates ###
BALANCE_TEXT="Actual Balance: %d nano\nAvailable Balance: %d nano\nPending Send: %d nano\nPending Receipt: %d nano"
DEPOSIT_TEXT="Your wallet address is %s\nQR: %s"
INSUFFICIENT_FUNDS_TEXT="You don't have enough nano to tip that much!"
TIP_ERROR_TEXT="Something went wrong with the tip. I wrote to logs."
HELP_INFO="!help or !man:\n Display this message"
BALANCE_INFO=("!balance:\n Displays the balance of your tip account as described:" +
		"\n - Actual Balance: The actual balance in your tip account" +
		"\n - Available Balance: The balance you are able to tip with (Actual - Pending Send)" +
		"\n - Pending Send: Tips you have sent, but have not yet been processed by the node" +
		"\n - Pending Receipt: Tips that have been sent to you, but have not yet been processed by the node. " +
		"\n Pending funds will be available for tip/withdraw after the transactions have been processed")
DEPOSIT_INFO=("!deposit or !register:\n Displays your tip bot account address along with a QR code" +
		"\n Send NANO to this address to increase your tip bot balance" +
		"\n If you do not have a tip bot account yet, this command will create one for you")
WITHDRAW_INFO="!withdraw <address>:\n Withdraws your entire tip account balance to the specified address"
TIP_INFO=("!tip <amount> <*users>:\n Tip specified amount to mentioned user(s) (minimum tip is 1 nano)" +
		"\n Tip units are in 1/1000000th of NANO. 1 nano = 0.000001 NANO" +
		"\n The recipient(s) will be notified of your tip via private message" +
		"\n Successful tips will be deducted from your available balance immediately")
RAIN_INFO=("!rain <amount>:\n Distribute <amount> to online users who have posted in the last 30 minutes" +
		"\n Only pulls users who have posted in the current channel within the last 30 minutes" +
		"\n Minimum amount required: " + str(RAIN_MINIMUM))
LEADERBOARD_INFO="!bigtippers or !leaderboard:\n Display the all-time tip leaderboard"
STATS_INFO="!tipstats:\n Display your personal tipping stats (rank, total tipped, and average tip)"
SETTIP_INFO=("!settiptotal <user>:\n Manually set the 'total tipped' for a user (for tip leaderboard)" +
		"\n This command is role restricted and only available to users with certain roles (e.g. Moderators)")
SETCOUNT_INFO=("!settipcount <user>:\n Manually set the 'tip count' for a user (for average tip statistic)" +
		"\n This command is role restricted and only available to users with certain roles (e.g. Moderators)")
HELP_TEXT=("NanoTipBot v%s - An open source NANO tip bot for Discord\n" +
		"Developed by <@303599885800964097> - Feel free to send suggestions, ideas, and/or tips\n" +
		"Supported Commands:\n" +
		"```" +
		HELP_INFO + "\n\n" +
		BALANCE_INFO + "\n\n" +
		DEPOSIT_INFO + "\n\n" +
		WITHDRAW_INFO + "\n\n" +
		TIP_INFO + "\n\n" +
		RAIN_INFO + "\n\n" +
		LEADERBOARD_INFO + "\n\n" +
		STATS_INFO + "\n\n" +
#		SETTIP_INFO + "\n\n" +
#		SETCOUNT_INFO +
		"\n\n\nsend node```" +
		"Source code: https://github.com/bbedward/NANO-Tip-Bot")
TIP_RECEIVED_TEXT="You were tipped %d nano by %s"
TIP_USAGE="Usage:\n```" + TIP_INFO + "```"
WITHDRAW_SUCCESS_TEXT="Withdraw has been queued for processing"
WITHDRAW_PROCESSED_TEXT="Withdraw processed TXID: %s" #TODO
WITHDRAW_NO_BALANCE_TEXT="You have no nano to withdraw"
WITHDRAW_ADDRESS_NOT_FOUND_TEXT="Usage:\n```" + WITHDRAW_INFO + "```"
WITHDRAW_INVALID_ADDRESS_TEXT="Withdraw address is not valid"
WITHDRAW_ERROR_TEXT="Something went wrong ! :thermometer_face: "
TOP_HEADER_TEXT="Here are the top %d tippers :clap:"
TOP_HEADER_EMPTY_TEXT="The leaderboard is empty!"
TOP_SPAM="No more big tippers for %d seconds"
STATS_ACCT_NOT_FOUND_TEXT="I could not find an account for you, try private messaging me !register"
STATS_TEXT="You are rank #%d, have tipped a total of %.6f NANO, with an average tip of %.6f NANO"
SET_TOTAL_USAGE="Usage:\n```" + SETTIP_INFO + "```"
SET_COUNT_USAGE="Usage:\n```" + SETCOUNT_INFO + "```"
RAIN_USAGE="Usage:\n```" + RAIN_INFO + "```"
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
				raw_withdraw_amt = str(amount) + '000000000000000000000000'
				wallet_command = {
					'action': 'send',
					'wallet': settings.wallet,
					'source': src_addr,
					'destination': to_addr,
					'amount': int(raw_withdraw_amt),
					'id': uid
				}
				wallet_output = wallet.communicate_wallet(wallet_command)
				if 'block' in wallet_output:
					txid = wallet_output['block']
				else:
					txid = 'invalid'
				db.mark_transaction_processed(uid, txid)
				logger.info('TX processed. UID: %s, TXID: %s', uid, txid)
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
	logger.info("NANO Tip Bot v%s started", BOT_VERSION)
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
	if ctx.message.channel.is_private:
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
async def tip(ctx):
	if ctx.message.channel.is_private:
		return

	try:
		amount = find_amount(ctx.message.content)
		# Make sure amount is valid and user has specified at least 1 recipient
		if amount < 1 or len(ctx.message.mentions) < 1:
			await post_dm(ctx.message.author, TIP_USAGE)
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
				await post_dm(member, TIP_RECEIVED_TEXT, amount, ctx.message.author.name)
		# Post message reactions
		await react_to_message(ctx.message, required_amt)
	except util.TipBotException as e:
		if e.error_type == "amount_not_found":
			await post_dm(ctx.message.author, TIP_USAGE)
		if e.error_type == "error":
			await post_response(ctx.message, TIP_ERROR_TEXT)

@client.command(pass_context=True)
async def rain(ctx):
	if ctx.message.channel.is_private:
		return
	try:
		amount = find_amount(ctx.message.content)
		balance = wallet.get_balance_adj(ctx.message.author.id)
		# Make sure amount meets requirements
		if amount < RAIN_MINIMUM:
			await post_dm(ctx.message.author, RAIN_USAGE)
			return
		elif balance < RAIN_MINIMUM:
			await post_dm(ctx.message.author, INSUFFICIENT_FUNDS_TEXT)
		since_ts = datetime.datetime.now() - datetime.timedelta(minutes=30)
		users_to_tip = []
		async for msg in client.logs_from(ctx.message.channel, limit=500, after=since_ts):
			if msg.author.id not in settings.exempt_users and msg.author.id != ctx.message.author.id:
				users_to_tip.append(msg.author.id)
		# Make the list distinct by making it a set
		users_to_tip = list(set(users_to_tip))
		if len(users_to_tip) < 1:
			return # Ops
		# Get individual tip amount
		tip_amount = int(amount / len(users_to_tip))
		for user_id in users_to_tip:
			user = await client.get_user_info(user_id)
			if user is None:
				continue
			uid = str(uuid.uuid4())
			wallet.make_transaction_to_user(ctx.message.author.id, amount, user.id, user.name, uid)
			await post_dm(user, TIP_RECEIVED_TEXT, tip_amount, ctx.message.author.name)
		# Post message reactions
		await react_to_message(ctx.message, amount)
		await client.add_reaction(ctx.message, '\U0001F4A6') # Sweat Drops
	except util.TipBotException as e:
		if e.error_type == "amount_not_found":
			await post_dm(ctx.message.author, RAIN_USAGE)

@client.command(pass_context=True, aliases=['leaderboard'])
async def bigtippers(ctx):
	# Check spam
	global last_big_tippers
	if not ctx.message.channel.is_private:
		tdelta = datetime.datetime.now() - last_big_tippers
		if SPAM_THRESHOLD > tdelta.seconds:
			await post_response(ctx.message, TOP_SPAM, (SPAM_THRESHOLD - tdelta.seconds))
			return
		last_big_tippers = datetime.datetime.now()
	top_users = db.get_top_users(TOP_TIPPERS_COUNT)
	if len(top_users) == 0:
		await post_response(ctx.message, TOP_HEADER_EMPTY_TEXT)
	else:
		# Probably a very clunky and sloppy way to format this output, I'm sure there's something better
		response = TOP_HEADER_TEXT % TOP_TIPPERS_COUNT
		response += "```"
		max_l = 0
		top_user_nms = []
		for top_user in top_users:
			if top_user['index'] >= 10:
				top_user_nm = '%d: %s ' % (top_user['index'], top_user['name'])
			else:
				top_user_nm = '%d:  %s ' % (top_user['index'], top_user['name'])
			if len(top_user_nm) > max_l:
				max_l = len(top_user_nm)
			top_user_nms.append(top_user_nm)

		for top_user in top_users:
			top_user_nm = top_user_nms[top_user['index'] - 1]
			padding = " " * ((max_l - len(top_user_nm)) + 1)
			response += top_user_nm
			response += padding
			response += '- %.6f NANO' % top_user['amount']
			response += '\n'
		response += "```"
		await post_response(ctx.message, response)

@client.command(pass_context=True)
async def tipstats(ctx):
	tip_stats = db.get_tip_stats(ctx.message.author.id)
	if tip_stats is None or len(tip_stats) == 0:
		await post_response(ctx.message, STATS_ACCT_NOT_FOUND_TEXT)
		return
	await post_response(ctx.message, STATS_TEXT, tip_stats['rank'], tip_stats['total'], tip_stats['average'])

@client.command(pass_context=True)
@commands.has_any_role(*settings.admin_roles)
async def settiptotal(ctx, amount: float = -1.0, user: discord.Member = None):
	if user is None or amount < 0:
		await post_response(ctx.message, SET_TOTAL_USAGE)
		return
	db.update_tip_total(user.id, amount)

@client.command(pass_context=True)
@commands.has_any_role(*settings.admin_roles)
async def settipcount(ctx, cnt: int = -1, user: discord.Member = None):
	if user is None or cnt < 0:
		await post_response(ctx.message, SET_COUNT_USAGE)
		return
	db.update_tip_count(user.id, cnt)

### Utility Functions
def get_qr_url(text):
	return 'https://chart.googleapis.com/chart?cht=qr&chl=%s&chs=180x180&choe=UTF-8&chld=L|2' % text

def find_address(input_text):
	address = input_text.split(' ')
	if len(address) == 1:
		raise util.TipBotException("address_not_found")
	elif address[1] is None:
		raise util.TipBotException("address_not_found")
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
		response = "<@" + message.author.id + "> \n" + response
	logger.info("sending response: '%s' to message: %s", response, message.content)
	await client.send_message(message.channel, response)


async def post_dm(member, template, *args):
	response = template % tuple(args)
	logger.info("sending dm: '%s' to user: %s", response, member.id)
	await client.send_message(member, response)

async def post_dm_id(user_id, template, *args):
	await post_dm(await client.get_user_info(user_id), template, args)

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

