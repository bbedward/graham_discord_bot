import discord
from discord.ext import commands
from discord.ext.commands import Bot
import threading
from threading import Thread
from queue import Queue
import atexit
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

BOT_VERSION = "1.8.1"

# How many users to display in the top users count
TOP_TIPPERS_COUNT=15
# How many previous giveaway winners to display
WINNERS_COUNT=10
# Minimum Amount for !rain
RAIN_MINIMUM = settings.rain_minimum
# Minimum amount for !startgiveaway
GIVEAWAY_MINIMUM = settings.giveaway_minimum
# Giveaway duration
GIVEAWAY_DURATION = 60
# Rain Delta (Minutes) - How long to look back for active users for !rain
RAIN_DELTA=30
# Spam Threshold (Seconds) - how long to output certain commands (e.g. bigtippers)
SPAM_THRESHOLD=60
# Withdraw Cooldown (Seconds) - how long a user must wait between withdraws
WITHDRAW_COOLDOWN=300
# MAX TX_Retries - If wallet does not indicate a successful send for whatever reason, retry this many times
MAX_TX_RETRIES=3
# Change command prefix to whatever you want to begin commands with
COMMAND_PREFIX=settings.command_prefix
# Withdraw Check Job - checks for completed withdraws at this interval
WITHDRAW_CHECK_JOB=15
# Pool giveaway auto amount (1%)
TIPGIVEAWAY_AUTO_ENTRY=int(.01 * GIVEAWAY_MINIMUM)

# Spam prevention
spam_delta=datetime.datetime.now() - datetime.timedelta(seconds=SPAM_THRESHOLD)
last_big_tippers=spam_delta
last_top_tips=spam_delta
last_winners=spam_delta

### Response Templates ###
COMMAND_NOT_FOUND="I don't understand what you're saying, try %shelp" % COMMAND_PREFIX
BALANCE_INFO=("%sbalance:\n Displays the balance of your tip account (in naneroo) as described:" +
		"\n - Actual Balance: The actual balance in your tip account" +
		"\n - Available Balance: The balance you are able to tip with (Actual - Pending Send)" +
		"\n - Pending Send: Tips you have sent, but have not yet been processed by the node" +
		"\n - Pending Receipt: Tips that have been sent to you, but have not yet been processed by the node. " +
		"\n Pending funds will be available for tip/withdraw after the transactions have been processed") % COMMAND_PREFIX
DEPOSIT_INFO=("%sdeposit or %sregister:\n Displays your tip bot account address along with a QR code" +
		"\n Send NANO to this address to increase your tip bot balance" +
		"\n If you do not have a tip bot account yet, this command will create one for you") % (COMMAND_PREFIX,COMMAND_PREFIX)
WITHDRAW_INFO="%swithdraw <address> <(optional) amount>:\n Withdraws specified amount to specified address, if amount isn't specified your entire tip account balance will be withdrawn" % COMMAND_PREFIX
TIP_INFO=("%stip <amount> <*users>:\n Tip specified amount to mentioned user(s) (minimum tip is 1 naneroo)" +
		"\n Tip units are in 1/1000000th of NANO. 1 naneroo = 0.000001 NANO" +
		"\n The recipient(s) will be notified of your tip via private message" +
		"\n Successful tips will be deducted from your available balance immediately") % COMMAND_PREFIX
TIPSPLIT_INFO="%stipsplit <amount> <*users>:\n Distribute <amount> evenly to all mentioned users" % COMMAND_PREFIX
RAIN_INFO=("%srain <amount>:\n Distribute <amount> evenly to users who are eligible." +
		"\n To receive rain you must:" +
		"\n - Have used this tip bot before" +
		"\n - Must be online and have been actively contributing around the time a rain occurs" +
		"\n Note: Spamming messages in a short period of time does not make you rain eligible" +
		"\n Minimum rain amount: %d naneroo") % (COMMAND_PREFIX, RAIN_MINIMUM)
START_GIVEAWAY_INFO=("%sgivearai or %ssponsorgiveaway <amount> <entry_fee>:\n Start a giveaway with given amount and entry fee (in naneroo)." +
		"\n Entry costs are added to the total prize pool"
		"\n Minimum amount to start giveaway: %d naneroo" +
		"\n Giveaway will end and choose random winner after 60 minutes") % (COMMAND_PREFIX, COMMAND_PREFIX, GIVEAWAY_MINIMUM)
ENTER_INFO="%sticket or %sentergiveaway:\n Enter the current giveaway, if there is one" % (COMMAND_PREFIX, COMMAND_PREFIX)
TIPGIVEAWAY_INFO="%stipgiveaway or %sdonate <amount>\n Add <amount> to the current giveaway pool\n If there is no giveaway, one will be started when minimum is reached.\n Tips >= %d naneroo automatically enter you for giveaways sponsored by the community (Not for giveaways sponsored by individuals)" % (COMMAND_PREFIX, COMMAND_PREFIX, TIPGIVEAWAY_AUTO_ENTRY)
TICKETSTATUS_INFO="%sticketstatus\n Check your current entry status for the current or future giveaway" % COMMAND_PREFIX
GIVEAWAY_STATS_INFO="%sgiveawaystats or %sgoldenticket:\n Display statistics relevant to the current giveaway" % (COMMAND_PREFIX, COMMAND_PREFIX)
WINNERS_INFO="%swinners:\n Display previous giveaway winners" % COMMAND_PREFIX
LEADERBOARD_INFO="%sleaderboard:\n Display the all-time tip leaderboard" % COMMAND_PREFIX
TOPTIPS_INFO="%stoptips:\n Display the single largest tips for the past 24 hours, current month, and all time" % COMMAND_PREFIX
STATS_INFO="%stipstats:\n Display your personal tipping stats (rank, total tipped, and average tip)" % COMMAND_PREFIX
SETTIP_INFO=("%ssettiptotal <user>:\n Manually set the 'total tipped' for a user (for tip leaderboard)" +
		"\n This command is role restricted and only available to users with certain roles (e.g. Moderators)") % COMMAND_PREFIX
SETCOUNT_INFO=("%ssettipcount <user>:\n Manually set the 'tip count' for a user (for average tip statistic)" +
		"\n This command is role restricted and only available to users with certain roles (e.g. Moderators)") % COMMAND_PREFIX
HELP_TEXT_1=("NanoTipBot v%s - An open source NANO tip bot for Discord\n" +
		"Developed by <@303599885800964097> - Feel free to send suggestions, ideas, and/or tips\n")
HELP_TEXT_2=("Account Commands:\n" +
		"```" +
		BALANCE_INFO + "\n\n" +
		DEPOSIT_INFO + "\n\n" +
		WITHDRAW_INFO + "\n\n" +
		"```")
HELP_TEXT_3=("Tip Commands:\n" +
		"```" +
		TIP_INFO + "\n\n" +
		TIPSPLIT_INFO + "\n\n" +
		RAIN_INFO + "\n\n" +
		START_GIVEAWAY_INFO + "\n\n" +
		ENTER_INFO + "\n\n" +
		TIPGIVEAWAY_INFO + "\n\n" +
		TICKETSTATUS_INFO + "\n\n"
		"```");
HELP_TEXT_4=("Stats Commands:\n" +
		"```" +
		LEADERBOARD_INFO + "\n\n" +
		STATS_INFO + "\n\n" +
		TOPTIPS_INFO + "\n\n" +
#              SETTIP_INFO + "\n\n" +
#              SETCOUN_INFO +
		GIVEAWAY_STATS_INFO + "\n\n" +
		WINNERS_INFO +
                "\n\n\nsend node```" +
                "Source code: https://github.com/bbedward/NANO-Tip-Bot")
BOT_DESCRIPTION=("NanoTipBot v%s - An open source NANO tip bot for Discord\n" +
		"Developed by <@303599885800964097> - Feel free to send suggestions, ideas, and/or tips\n" +
		"Source: Source code: https://github.com/bbedward/NANO-Tip-Bot")
BALANCE_TEXT=(	"```Actual Balance   : %s naneroo (%.6f NANO)\n" +
		"Available Balance: %s naneroo (%.6f NANO)\n" +
		"Pending Send     : %s naneroo (%.6f NANO)\n" +
		"Pending Receipt  : %s naneroo (%.6f NANO)```")
DEPOSIT_TEXT="Your wallet address is:"
DEPOSIT_TEXT_2="%s"
DEPOSIT_TEXT_3="QR: %s"
INSUFFICIENT_FUNDS_TEXT="You don't have enough nano in your available balance!"
TIP_ERROR_TEXT="Something went wrong with the tip. I wrote to logs."
TIP_RECEIVED_TEXT="You were tipped %d naneroo by %s"
TIP_USAGE="Usage:\n```" + TIP_INFO + "```"
TIP_SELF="No valid recipients found in your tip.\n(You cannot tip yourself and certain other users are exempt from receiving tips)"
WITHDRAW_SUCCESS_TEXT="Withdraw has been queued for processing, I'll send you a link to the transaction after I've broadcasted it to the network!"
WITHDRAW_PROCESSED_TEXT="Withdraw processed:\nTransaction: https://www.nanode.co/block/%s\nIf you have an issue with a withdraw please wait 24 hours before contacting me, the issue will likely resolve itself."
WITHDRAW_NO_BALANCE_TEXT="You have no NANO to withdraw"
WITHDRAW_ADDRESS_NOT_FOUND_TEXT="Usage:\n```" + WITHDRAW_INFO + "```"
WITHDRAW_INVALID_ADDRESS_TEXT="Withdraw address is not valid"
WITHDRAW_ERROR_TEXT="Something went wrong ! :thermometer_face: "
WITHDRAW_COOLDOWN_TEXT="You need to wait %d seconds before making another withdraw"
WITHDRAW_INSUFFICIENT_BALANCE="Your balance isn't high enough to withdraw that much"
TOP_HEADER_TEXT="Here are the top %d tippers :clap:"
TOP_HEADER_EMPTY_TEXT="The leaderboard is empty!"
TOP_SPAM="No more big tippers for %d seconds"
STATS_ACCT_NOT_FOUND_TEXT="I could not find an account for you, try private messaging me `%sregister`" % COMMAND_PREFIX
STATS_TEXT="You are rank #%d, you've tipped a total of %.6f NANO, your average tip is %.6f NANO, and your biggest tip of all time is %.6f NANO"
SET_TOTAL_USAGE="Usage:\n```" + SETTIP_INFO + "```"
SET_COUNT_USAGE="Usage:\n```" + SETCOUNT_INFO + "```"
TIPSPLIT_USAGE="Usage:\n```" + TIPSPLIT_INFO + "```"
TIPSPLIT_SMALL="Tip amount is too small to be distributed to that many users"
RAIN_USAGE="Usage:\n```" + RAIN_INFO + "```"
RAIN_NOBODY="I couldn't find anybody eligible to receive rain"
GIVEAWAY_EXISTS="There's already an active giveaway"
GIVEAWAY_USAGE="Usage:\n```" + START_GIVEAWAY_INFO + "```"
GIVEAWAY_STARTED="%s has sponsored a giveaway of %.6f NANO! Use:\n - `" + COMMAND_PREFIX + "ticket` to enter\n - `" + COMMAND_PREFIX + "donate` to increase the pot\n - `" + COMMAND_PREFIX + "ticketstatus` to check the status of your entry"
GIVEAWAY_STARTED_FEE="%s has sponsored a giveaway of %.6f NANO! The entry fee is %d naneroo. Use:\n - `" + COMMAND_PREFIX + "ticket %d` to buy your ticket\n - `" + COMMAND_PREFIX + "donate` to increase the pot\n - `" + COMMAND_PREFIX + "ticketstatus` to check the status of your entry"
GIVEAWAY_MAX_FEE="Giveaway entry fee cannot be more than 5% of the prize pool"
GIVEAWAY_ENDED="Congratulations! <@%s> was the winner of the giveaway! They have been sent %.6f NANO!"
GIVEAWAY_STATS="There are %d entries to win %.6f NANO ending in %s - sponsored by %s.\nUse:\n - `" + COMMAND_PREFIX + "ticket` to enter\n -`" + COMMAND_PREFIX + "donate` to add to the pot\n - `" + COMMAND_PREFIX + "ticketstatus` to check status of your entry"
GIVEAWAY_STATS_FEE="There are %d entries to win %.6f NANO ending in %s - sponsored by %s.\nEntry fee: %d naneroo. Use:\n - `" + COMMAND_PREFIX + "ticket %d` to enter\n - `" + COMMAND_PREFIX + "donate` to add to the pot\n - `" + COMMAND_PREFIX + "ticketstatus` to check the status of your entry"
GIVEAWAY_STATS_INACTIVE="There are no active giveaways\n%d naneroo required to to automatically start one! Donate to the pot using `" + COMMAND_PREFIX + "donate`. You can also sponsor one using `" + COMMAND_PREFIX + "givearai`"
ENTER_ADDED="You've been successfully entered into the giveaway"
ENTER_DUP="You've already entered the giveaway"
TIPGIVEAWAY_USAGE="Usage:\n```" + TIPGIVEAWAY_INFO + "```"
TIPGIVEAWAY_NO_ACTIVE="There are no active giveaways. Check giveaway status using `%sgiveawaystats`, or donate to the next one using `%stipgiveaway`" % (COMMAND_PREFIX, COMMAND_PREFIX)
TIPGIVEAWAY_ENTERED_FUTURE="With your gorgeous donation I have reserved your ticket for the next community sponsored giveaway!"
TOPTIP_SPAM="No more top tips for %d seconds"
PAUSE_MSG="All transaction activity is currently suspended. Check back later."
BAN_SUCCESS="User %s can no longer receive tips"
BAN_DUP="User %s is already banned"
UNBAN_SUCCESS="User %s has been unbanned"
UNBAN_DUP="User %s is not banned"
STATSBAN_SUCCESS="User %s is no longer considered in tip statistics"
STATSBAN_DUP="User %s is already stats banned"
STATSUNBAN_SUCCESS="User %s is now considered in tip statistics"
STATSUNBAN_DUP="User %s is not stats banned"
WINNERS_HEADER="Here are the previous %d giveaway winners! :trophy:" % WINNERS_COUNT
WINNERS_EMPTY="There are no previous giveaway winners"
WINNERS_SPAM="No more winners for %d seconds"
### END Response Templates ###

# Paused flag, indicates whether or not bot is paused
paused = False

# Create discord client
client = Bot(command_prefix=COMMAND_PREFIX, description=BOT_DESCRIPTION)
client.remove_command('help')

# Thread to process send transactions
# Queue is used to communicate back to main thread
withdrawq = Queue()
class SendProcessor(Thread):
	def __init__(self):
		super(SendProcessor, self).__init__()
		self._stop_event = threading.Event()

	def run(self):
		while True:
			# Just so we don't constantly berate the database if there's no TXs to chew through
			time.sleep(10)
			txs = db.get_unprocessed_transactions()
			for tx in txs:
				if self.stopped():
					break
				source_address = tx['source_address']
				to_address = tx['to_address']
				amount = tx['amount']
				uid = tx['uid']
				attempts = tx['attempts']
				raw_withdraw_amt = str(amount) + '000000000000000000000000'
				wallet_command = {
					'action': 'send',
					'wallet': settings.wallet,
					'source': source_address,
					'destination': to_address,
					'amount': int(raw_withdraw_amt),
					'id': uid
				}
				src_usr = db.get_user_by_wallet_address(source_address)
				trg_usr = db.get_user_by_wallet_address(to_address)
				source_id=None
				target_id=None
				pending_delta = int(amount) * -1
				if src_usr is not None:
					source_id=src_usr.user_id
				if trg_usr is not None:
					target_id=trg_usr.user_id
				db.mark_transaction_sent(uid, pending_delta, source_id, target_id)
				logger.debug("RPC Send")
				try:

					wallet_output = wallet.communicate_wallet(wallet_command)
				except Exception as e:
					logger.exception(e)
					continue
				logger.debug("RPC Response")
				if 'block' in wallet_output:
					txid = wallet_output['block']
					db.mark_transaction_processed(uid, txid)
					logger.info('TX processed. UID: %s, TXID: %s', uid, txid)
					if target_id is None:
						withdrawq.put({'user_id':source_id, 'txid':txid})
				else:
					# Not sure what happen but we'll retry a few times
					if attempts >= MAX_TX_RETRIES:
						logger.info("Max Retires Exceeded for TX UID: %s", uid)
						db.mark_transaction_processed(uid, 'invalid')
					else:
						db.inc_tx_attempts(uid)
			if self.stopped():
				break

	def stop(self):
		self._stop_event.set()

	def stopped(self):
		return self._stop_event.is_set()

# Start bot, print info
sp = SendProcessor()

def handle_exit():
	sp.stop()

@client.event
async def on_ready():
	logger.info("NANO Tip Bot v%s started", BOT_VERSION)
	logger.info("Discord.py API version %s", discord.__version__)
	logger.info("Name: %s", client.user.name)
	logger.info("ID: %s", client.user.id)
	await client.change_presence(game=discord.Game(name=settings.playing_status))
	logger.info("Starting SendProcessor Thread")
	if not sp.is_alive():
		sp.start()
	logger.info("Registering atexit handler")
	atexit.register(handle_exit)
	logger.info("Starting withdraw check job")
	asyncio.get_event_loop().create_task(check_for_withdraw())
	logger.info("Continuing outstanding giveaway")
	asyncio.get_event_loop().create_task(start_giveaway_timer())

async def check_for_withdraw():
	try:
		await asyncio.sleep(WITHDRAW_CHECK_JOB)
		asyncio.get_event_loop().create_task(check_for_withdraw())
		while not withdrawq.empty():
			withdraw = withdrawq.get(block=False)
			if withdraw is None:
				continue
			user_id = withdraw['user_id']
			txid = withdraw['txid']
			user = await client.get_user_info(user_id)
			await post_dm(user, WITHDRAW_PROCESSED_TEXT, txid)
	except Exception as ex:
		logger.exception(ex)

# Override on_message and do our spam check here
@client.event
async def on_message(message):
	# disregard messages sent by our own bot
	if message.author.id == client.user.id:
		return

	if db.last_msg_check(message.author.id, message.content, message.channel.is_private) == False:
		return
	await client.process_commands(message)


def has_admin_role(roles):
	for r in roles:
		if r.name in settings.admin_roles:
			return True
	return False

async def pause_msg(message):
	if paused:
		await post_dm(message.author, PAUSE_MSG)

async def is_admin(user):
	return (has_admin_role(user.roles) or user.id in settings.admin_ids)

### Commands
@client.command(pass_context=True)
async def help(ctx):
	message = ctx.message
	if message.channel.is_private:
		# Four messages because discord API responds in error with our really long help text
		await post_response(message, HELP_TEXT_1, BOT_VERSION)
		await post_response(message, HELP_TEXT_2)
		await post_response(message, HELP_TEXT_3)
		await post_response(message, HELP_TEXT_4)

@client.command(pass_context=True)
async def balance(ctx):
	message = ctx.message
	if message.channel.is_private:
		user = db.get_user_by_id(message.author.id)
		if user is None:
			return
		bal_msg = await post_response(message, "Retrieving balance...")
		balances = await wallet.get_balance(user)
		actual = balances['actual']
		actualnano = actual / 1000000
		available = balances['available']
		availablenano = available / 1000000
		send = balances['pending_send']
		sendnano = send / 1000000
		receive = balances['pending']
		receivenano = receive / 1000000
		await post_edit(bal_msg, BALANCE_TEXT,		"{:,}".format(actual),
								actualnano,
								"{:,}".format(available),
								availablenano,
								"{:,}".format(send),
								sendnano,
								"{:,}".format(receive),
								receivenano)

@client.command(pass_context=True, aliases=['register'])
async def deposit(ctx):
	message = ctx.message
	if message.channel.is_private:
		user = await wallet.create_or_fetch_user(message.author.id, message.author.name)
		user_deposit_address = user.wallet_address
		await post_response(message, DEPOSIT_TEXT)
		await post_response(message, DEPOSIT_TEXT_2, user_deposit_address)
		await post_response(message, DEPOSIT_TEXT_3, get_qr_url(user_deposit_address))

@client.command(pass_context=True)
async def withdraw(ctx):
	message = ctx.message
	if paused:
		await pause_msg(message)
		return
	if message.channel.is_private:
		try:
			withdraw_amount = find_amount(message.content)
		except util.TipBotException as e:
			withdraw_amount = 0
		try:
			withdraw_address = find_address(message.content)
			user = db.get_user_by_id(message.author.id)
			if user is None:
				return
			last_withdraw_delta = db.get_last_withdraw_delta(user.user_id)
			if WITHDRAW_COOLDOWN > last_withdraw_delta:
				await post_response(message, WITHDRAW_COOLDOWN_TEXT, (WITHDRAW_COOLDOWN - last_withdraw_delta))
				return
			source_id = user.user_id
			source_address = user.wallet_address
			balance = await wallet.get_balance(user)
			amount = balance['available']
			if withdraw_amount == 0:
				withdraw_amount = amount
			else:
				withdraw_amount = abs(withdraw_amount)
			if amount == 0:
				await post_response(message, WITHDRAW_NO_BALANCE_TEXT)
			elif withdraw_amount > amount:
				await post_response(message, WITHDRAW_INSUFFICIENT_BALANCE)
			else:
				uid = str(uuid.uuid4())
				await wallet.make_transaction_to_address(user, withdraw_amount, withdraw_address, uid,verify_address = True)
				await post_response(message, WITHDRAW_SUCCESS_TEXT)
		except util.TipBotException as e:
			if e.error_type == "address_not_found":
				await post_response(message, WITHDRAW_ADDRESS_NOT_FOUND_TEXT)
			elif e.error_type == "invalid_address":
				await post_response(message, WITHDRAW_INVALID_ADDRESS_TEXT)
			elif e.error_type == "balance_error":
				await post_response(message, INSUFFICIENT_FUNDS_TEXT)
			elif e.error_type == "error":
				await post_response(message, WITHDRAW_ERROR_TEXT)

@client.command(pass_context=True)
async def tip(ctx):
	message = ctx.message
	if message.channel.is_private:
		return
	elif paused:
		await pause_msg(message)
		return

	try:
		amount = find_amount(message.content)
		# Make sure amount is valid and at least 1 user is mentioned
		if amount < 1 or len(message.mentions) < 1:
			raise util.TipBotException("usage_error")
		# Create tip list
		users_to_tip = []
		for member in message.mentions:
			# Disregard mentions of exempt users and self
			if member.id not in settings.exempt_users and member.id != message.author.id and not db.is_banned(member.id) and not member.bot:
				users_to_tip.append(member)
		if len(users_to_tip) < 1:
			raise util.TipBotException("no_valid_recipient")
		# Cut out duplicate mentions
		users_to_tip = list(set(users_to_tip))
		# Make sure this user has enough in their balance to complete this tip
		required_amt = amount * len(users_to_tip)
		user = db.get_user_by_id(message.author.id)
		balance = await wallet.get_balance(user)
		user_balance = balance['available']
		if user_balance < required_amt:
			await add_x_reaction(message)
			await post_dm(message.author, INSUFFICIENT_FUNDS_TEXT)
			return
		# Distribute tips
		for member in users_to_tip:
			uid = str(uuid.uuid4())
			actual_amt = await wallet.make_transaction_to_user(user, amount, member.id, member.name, uid)
			# Something went wrong, tip didn't go through
			if actual_amt == 0:
				required_amt -= amount
			else:
				await post_dm(member, TIP_RECEIVED_TEXT, actual_amt, message.author.name)
		# Post message reactions
		await react_to_message(message, required_amt)
		# Update tip stats
		db.update_tip_stats(user, required_amt)
	except util.TipBotException as e:
		if e.error_type == "amount_not_found" or e.error_type == "usage_error":
			await post_dm(message.author, TIP_USAGE)
		elif e.error_type == "no_valid_recipient":
			await post_dm(message.author, TIP_SELF)
		else:
			await post_response(message, TIP_ERROR_TEXT)

@client.command(pass_context=True)
async def tipsplit(ctx):
	message = ctx.message
	if message.channel.is_private:
		return
	elif paused:
		await pause_msg(message)
	try:
		amount = find_amount(message.content)
		# Make sure amount is valid and at least 1 user is mentioned
		if amount < 1 or len(message.mentions) < 1:
			raise util.TipBotException("usage_error")
		if int(amount / len(message.mentions)) < 1:
			raise util.TipBotException("invalid_tipsplit")
		# Create tip list
		users_to_tip = []
		for member in message.mentions:
			# Disregard mentions of self and exempt users
			if member.id not in settings.exempt_users and member.id != message.author.id and not db.is_banned(member.id) and not member.bot:
				users_to_tip.append(member)
		if len(users_to_tip) < 1:
			raise util.TipBotException("no_valid_recipient")
		# Remove duplicates
		users_to_tip = list(set(users_to_tip))
		# Make sure user has enough in their balance
		user = db.get_user_by_id(message.author.id)
		if user is None:
			return
		balance = await wallet.get_balance(user)
		user_balance = balance['available']
		if user_balance < amount:
			await add_x_reaction(ctx.message)
			await post_dm(message.author, INSUFFICIENT_FUNDS_TEXT)
			return
		# Distribute tips
		tip_amount = int(amount / len(users_to_tip))
		# Recalculate amount as it may be different since truncating decimal
		real_amount = tip_amount * len(users_to_tip)
		for member in users_to_tip:
			uid = str(uuid.uuid4())
			actual_amt = await wallet.make_transaction_to_user(user, tip_amount, member.id, member.name, uid)
			# Tip didn't go through
			if actual_amt == 0:
				amount -= tip_amount
			else:
				await post_dm(member, TIP_RECEIVED_TEXT, tip_amount, message.author.name)
		await react_to_message(message, amount)
		db.update_tip_stats(user, real_amount)
	except util.TipBotException as e:
		if e.error_type == "amount_not_found" or e.error_type == "usage_error":
			await post_dm(message.author, TIPSPLIT_USAGE)
		elif e.error_type == "invalid_tipsplit":
			await post_dm(message.author, TIPSPLIT_SMALL)
		elif e.error_type == "no_valid_recipient":
			await post_dm(message.author, TIP_SELF)
		else:
			await post_response(message, TIP_ERROR_TEXT)

@client.command(pass_context=True)
async def rain(ctx):
	message = ctx.message
	if message.channel.is_private:
		return
	elif paused:
		await pause_msg(message)
		return
	try:
		amount = find_amount(message.content)
		if amount < RAIN_MINIMUM:
			raise util.TipBotException("usage_error")
		# Create tip list
		users_to_tip = []
		active_user_ids = db.get_active_users(RAIN_DELTA)
		if len(active_user_ids) < 1:
			raise util.TipBotException("no_valid_recipient")
		for auid in active_user_ids:
			dmember = message.server.get_member(auid)
			if dmember is not None and (dmember.status == discord.Status.online or dmember.status == discord.Status.idle):
				if dmember.id not in settings.exempt_users and dmember.id != message.author.id and not db.is_banned(dmember.id) and not dmember.bot:
					users_to_tip.append(dmember)
		users_to_tip = list(set(users_to_tip))
		if len(users_to_tip) < 1:
			raise util.TipBotException("no_valid_recipient")
		if int(amount / len(users_to_tip)) < 1:
			raise util.TipBotException("invalid_tipsplit")
		user = db.get_user_by_id(message.author.id)
		if user is None:
			return
		balance = await wallet.get_balance(user)
		user_balance = balance['available']
		if user_balance < amount:
			await add_x_reaction(message)
			await post_dm(message.author, INSUFFICIENT_FUNDS_TEXT)
			return
		# Distribute Tips
		tip_amount = int(amount / len(users_to_tip))
		# Recalculate actual tip amount as it may be smaller now
		real_amount = tip_amount * len(users_to_tip)
		for member in users_to_tip:
			uid = str(uuid.uuid4())
			actual_amt = await wallet.make_transaction_to_user(user, tip_amount, member.id, member.name, uid)
			# Tip didn't go through for some reason
			if actual_amt == 0:
				amount -= tip_amount
			else:
				await post_dm(member, TIP_RECEIVED_TEXT, actual_amt, message.author.name)

		# Message React
		await react_to_message(message, amount)
		await client.add_reaction(message, '\U0001F4A6') # Sweat Drops
		db.update_tip_stats(user, real_amount,rain=True)
		db.mark_user_active(user)
	except util.TipBotException as e:
		if e.error_type == "amount_not_found" or e.error_type == "usage_error":
			await post_dm(message.author, RAIN_USAGE)
		elif e.error_type == "no_valid_recipient":
			await post_dm(message.author, RAIN_NOBODY)
		elif e.error_type == "invalid_tipsplit":
			await post_dm(message.author, TIPSPLIT_SMALL)
		else:
			await post_response(message, TIP_ERROR_TEXT)

@client.command(pass_context=True, aliases=['entergiveaway'])
async def ticket(ctx):
	message = ctx.message
	if not db.is_active_giveaway():
		db.ticket_spam_check(message.author.id)
		await post_dm(message.author, TIPGIVEAWAY_NO_ACTIVE)
		await remove_message(message)
		return
	giveaway = db.get_giveaway()
	if giveaway.entry_fee == 0:
		spam = db.ticket_spam_check(message.author.id,increment=False)
		entered = db.add_contestant(message.author.id, banned=spam)
		if entered:
			if not spam:
				await wallet.create_or_fetch_user(message.author.id, message.author.name)
			await post_dm(message.author, ENTER_ADDED)
		else:
			await post_dm(message.author, ENTER_DUP)
	else:
		if db.is_banned(message.author.id):
			await remove_message(message)
			return
		if db.contestant_exists(message.author.id):
			await post_dm(message.author, ENTER_DUP)
		else:
			await tip_giveaway(message,ticket=True)
	await remove_message(message)

@client.command(pass_context=True, aliases=['sponsorgiveaway'])
async def givearai(ctx):
	message = ctx.message
	if message.channel.is_private:
		return
	elif paused:
		await pause_msg(message)
		return
	try:
		# One giveaway at a time
		if db.is_active_giveaway():
			await post_dm(message.author, GIVEAWAY_EXISTS)
			return
		split_content = message.content.split(' ')
		if len(split_content) > 2:
			amount = find_amount(split_content[1])
			fee = find_amount(split_content[2])
		else:
			raise util.TipBotException("usage_error")
		if amount < GIVEAWAY_MINIMUM:
			raise util.TipBotException("usage_error")
		max_fee = int(0.05 * amount)
		if fee > max_fee:
			await post_response(message, GIVEAWAY_MAX_FEE)
			return
		if 0 > fee:
			raise util.TipBotException("usage_error")
		user = db.get_user_by_id(message.author.id)
		if user is None:
			return
		balance = await wallet.get_balance(user)
		user_balance = balance['available']
		if user_balance < amount:
			await add_x_reaction(message)
			await post_dm(message.author, INSUFFICIENT_FUNDS_TEXT)
			return
		end_time = datetime.datetime.now() + datetime.timedelta(minutes=GIVEAWAY_DURATION)
		nano_amt = amount / 1000000
		giveaway = db.start_giveaway(message.author.id, message.author.name, nano_amt, end_time, message.channel.id, entry_fee=fee)
		uid = str(uuid.uuid4())
		await wallet.make_transaction_to_address(user, amount, None, uid, giveaway_id=giveaway.id)
		if fee > 0:
			await post_response(message, GIVEAWAY_STARTED_FEE, message.author.name, nano_amt, fee, fee)
		else:
			await post_response(message, GIVEAWAY_STARTED, message.author.name, nano_amt)
		asyncio.get_event_loop().create_task(start_giveaway_timer())
		db.update_tip_stats(user, amount, giveaway=True)
		db.add_contestant(message.author.id, override_ban=True)
	except util.TipBotException as e:
		if e.error_type == "amount_not_found" or e.error_type == "usage_error":
			await post_dm(message.author, GIVEAWAY_USAGE)

@client.command(pass_context=True, aliases=['tipgiveaway'])
async def donate(ctx):
	await tip_giveaway(ctx.message)

async def tip_giveaway(message, ticket=False):
	if message.channel.is_private and not ticket:
		return
	elif paused:
		await pause_msg(message)
		return
	try:
		giveaway = db.get_giveaway()
		amount = find_amount(message.content)
		user = db.get_user_by_id(message.author.id)
		if user is None:
			return
		balance = await wallet.get_balance(user)
		user_balance = balance['available']
		if user_balance < amount:
			await add_x_reaction(message)
			await post_dm(message.author, INSUFFICIENT_FUNDS_TEXT)
			return
		nano_amt = amount / 1000000
		if giveaway is not None:
			db.add_tip_to_giveaway(nano_amt)
			giveawayid = giveaway.id
			fee = giveaway.entry_fee
		else:
			giveawayid = -1
			fee = TIPGIVEAWAY_AUTO_ENTRY
		contributions = amount + db.get_tipgiveaway_contributions(message.author.id, giveawayid)
		if ticket:
			if fee > contributions:
				owed = fee - contributions
				await post_dm(message.author, "You were NOT entered into the giveaway! The fee for this giveaway is %d naneroo, you may enter using `%sticket %d`", owed, COMMAND_PREFIX, owed)
				return
		uid = str(uuid.uuid4())
		await wallet.make_transaction_to_address(user, amount, None, uid, giveaway_id=giveawayid)
		if not ticket:
			await react_to_message(message, amount)
		# If eligible, add them to giveaway
		if contributions >= fee:
			if contributions >= (fee * 4):
				db.mark_user_active(user)
			entered = db.add_contestant(message.author.id, override_ban=True)
			if entered:
				if giveaway is None:
					await post_response(message, TIPGIVEAWAY_ENTERED_FUTURE)
				else:
					await post_dm(message.author, ENTER_ADDED)
			elif ticket:
				await post_dm(message.author, ENTER_DUP)
		# If tip sum is >= GIVEAWAY MINIMUM then start giveaway
		if giveaway is None:
			tipgiveaway_sum = db.get_tipgiveaway_sum()
			nano_amt = float(tipgiveaway_sum)/ 1000000
			if tipgiveaway_sum >= GIVEAWAY_MINIMUM:
				duration = int(GIVEAWAY_DURATION / 2)
				end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration)
				db.start_giveaway(client.user.id, client.user.name, 0, end_time, message.channel.id,entry_fee=fee)
				await post_response(message, GIVEAWAY_STARTED_FEE, client.user.name, nano_amt, fee, fee)
				asyncio.get_event_loop().create_task(start_giveaway_timer())
		# Update top tip
		db.update_tip_stats(user, amount, giveaway=True)
	except util.TipBotException as e:
		if e.error_type == "amount_not_found" or e.error_type == "usage_error":
			if ticket:
				await post_dm(message.author, "Usage: `%sticket (fee)`", COMMAND_PREFIX)
			else:
				await post_dm(message.author, TIPGIVEAWAY_USAGE)

@client.command(pass_context=True)
async def ticketstatus(ctx):
	message = ctx.message
	user = db.get_user_by_id(message.author.id)
	if user is not None:
		await post_dm(message.author, db.get_ticket_status(message.author.id))
	await remove_message(message)

@client.command(pass_context=True)
async def giveawaystats(ctx):
	message = ctx.message
	stats = db.get_giveaway_stats()
	if stats is None:
		for_next = GIVEAWAY_MINIMUM - db.get_tipgiveaway_sum()
		await post_response(message, GIVEAWAY_STATS_INACTIVE, for_next)
	else:
		end = stats['end'] - datetime.datetime.now()
		end_s = int(end.total_seconds())
		str_delta = time.strftime("%M Minutes and %S Seconds", time.gmtime(end_s))
		fee = stats['fee']
		if fee == 0:
			await post_response(message, GIVEAWAY_STATS, stats['entries'], stats['amount'], str_delta, stats['started_by'])
		else:
			await post_response(message, GIVEAWAY_STATS_FEE, stats['entries'], stats['amount'], str_delta, stats['started_by'], fee, fee)

async def start_giveaway_timer():
	giveaway = db.get_giveaway()
	if giveaway is None:
		return
	delta = (giveaway.end_time - datetime.datetime.now()).total_seconds()
	if delta <= 0:
		await finish_giveaway(0)
		return

	await finish_giveaway(delta)

async def finish_giveaway(delay):
	await asyncio.sleep(delay)
	giveaway = db.finish_giveaway()
	if giveaway is not None:
		channel = client.get_channel(giveaway.channel_id)
		response = GIVEAWAY_ENDED % (giveaway.winner_id, giveaway.amount + giveaway.tip_amount)
		await client.send_message(channel, response)
		await post_dm(await client.get_user_info(giveaway.winner_id), response)

@client.command(pass_context=True)
async def winners(ctx):
	message = ctx.message
	# Check spam
	global last_winners
	if not message.channel.is_private:
		tdelta = datetime.datetime.now() - last_winners
		if SPAM_THRESHOLD > tdelta.seconds:
			await post_response(message, WINNERS_SPAM, (SPAM_THRESHOLD - tdelta.seconds))
			return
		last_winners = datetime.datetime.now()
	winners = db.get_giveaway_winners(WINNERS_COUNT)
	if len(winners) == 0:
		await post_response(message, WINNERS_EMPTY)
	else:
		response = WINNERS_HEADER
		response += "```"
		max_l = 0
		winner_nms = []
		for winner in winners:
			if winner['index'] >= 10:
				winner_nm = '%d: %s ' % (winner['index'], winner['name'])
			else:
				winner_nm = '%d:  %s ' % (winner['index'], winner['name'])
			if len(winner_nm) > max_l:
				max_l = len(winner_nm)
			winner_nms.append(winner_nm)

		for winner in winners:
			winner_nm = winner_nms[winner['index'] - 1]
			padding = " " * ((max_l - len(winner_nm)) + 1)
			response += winner_nm
			response += padding
			response += 'won %.6f NANO' % winner['amount']
			response += '\n'
		response += "```"
		await post_response(message, response)

@client.command(pass_context=True, aliases=['bigtippers'])
async def leaderboard(ctx):
	message = ctx.message
	# Check spam
	global last_big_tippers
	if not message.channel.is_private:
		tdelta = datetime.datetime.now() - last_big_tippers
		if SPAM_THRESHOLD > tdelta.seconds:
			await post_response(message, TOP_SPAM, (SPAM_THRESHOLD - tdelta.seconds))
			return
		last_big_tippers = datetime.datetime.now()
	top_users = db.get_top_users(TOP_TIPPERS_COUNT)
	if len(top_users) == 0:
		await post_response(message, TOP_HEADER_EMPTY_TEXT)
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
		await post_response(message, response)

@client.command(pass_context=True)
async def toptips(ctx):
	message = ctx.message
	# Check spam
	global last_top_tips
	if not message.channel.is_private:
		tdelta = datetime.datetime.now() - last_top_tips
		if SPAM_THRESHOLD > tdelta.seconds:
			await post_response(message, TOPTIP_SPAM, (SPAM_THRESHOLD - tdelta.seconds))
			return
		last_top_tips = datetime.datetime.now()
	top_tips_msg = db.get_top_tips()
	await post_response(message, top_tips_msg)

@client.command(pass_context=True)
async def tipstats(ctx):
	message = ctx.message
	tip_stats = db.get_tip_stats(message.author.id)
	if tip_stats is None or len(tip_stats) == 0:
		await post_response(message, STATS_ACCT_NOT_FOUND_TEXT)
		return
	await post_response(message, STATS_TEXT, tip_stats['rank'], tip_stats['total'], tip_stats['average'],tip_stats['top'])

@client.command(pass_context=True)
async def banned(ctx):
	message = ctx.message
	if is_admin(message.author):
		await post_dm(message.author, db.get_banned())

@client.command(pass_context=True)
async def statsbanned(ctx):
	message = ctx.message
	if is_admin(message.author):
		await post_dm(message.author, db.get_statsbanned())

@client.command(pass_context=True)
async def pause(ctx):
	message = ctx.message
	if is_admin(message.author):
		global paused
		paused = True

@client.command(pass_context=True)
async def unpause(ctx):
	message = ctx.message
	if is_admin(message.author):
		global paused
		paused = True

@client.command(pass_context=True)
async def tipban(ctx):
	message = ctx.message
	if is_admin(message.author):
		for member in message.mentions:
			if member.id not in settings.admin_ids and not has_admin_role(member.roles):
				if db.ban_user(member.id):
					await post_dm(message.author, BAN_SUCCESS, member.name)
				else:
					await post_dm(message.author, BAN_DUP, member.name)

@client.command(pass_context=True)
async def statsban(ctx):
	message = ctx.message
	if is_admin(message.author):
		for member in message.mentions:
			if db.statsban_user(member.id):
				await post_dm(message.author, STATSBAN_SUCCESS, member.name)
			else:
				await post_dm(message.author, STATSBAN_DUP, member.name)

@client.command(pass_context=True)
async def tipunban(ctx):
	message = ctx.message
	if is_admin(message.author):
		for member in message.mentions:
			if db.unban_user(member.id):
				await post_dm(message.author, UNBAN_SUCCESS, member.name)
			else:
				await post_dm(message.author, UNBAN_DUP, member.name)

@client.command(pass_context=True)
async def statsunban(ctx):
	message = ctx.message
	if is_admin(message.author):
		for member in message.mentions:
			if db.statsunban_user(member.id):
				await post_dm(message.author, STATSUNBAN_SUCCESS, member.name)
			else:
				await post_dm(message.author, STATSUNBAN_DUP, member.name)

@client.command(pass_context=True)
async def settiptotal(ctx, amount: float = -1.0, user: discord.Member = None):
	if is_admin(ctx.message.author):
		if user is None or amount < 0:
			await post_dm(ctx.message.author, SET_TOTAL_USAGE)
			return
		db.update_tip_total(user.id, amount)

@client.command(pass_context=True)
async def settipcount(ctx, cnt: int = -1, user: discord.Member = None):
	if is_admin(ctx.message.author):
		if user is None or cnt < 0:
			await post_dm(ctx.message.author, SET_COUNT_USAGE)
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
async def post_response(message, template, *args, incl_mention=True):
	response = template % tuple(args)
	if not message.channel.is_private and incl_mention:
		response = "<@" + message.author.id + "> \n" + response
	logger.info("sending response: '%s' for message: '%s' to userid: '%s' name: '%s'", response, message.content, message.author.id, message.author.name)
	asyncio.sleep(0.05) # Slight delay to avoid discord bot responding above commands
	return await client.send_message(message.channel, response)


async def post_dm(member, template, *args):
	response = template % tuple(args)
	logger.info("sending dm: '%s' to user: %s", response, member.id)
	try:
		asyncio.sleep(0.05)
		return await client.send_message(member, response)
	except:
		return None

async def post_edit(message, template, *args):
	response = template % tuple(args)
	return await client.edit_message(message, response)

async def remove_message(message):
	client_member = message.server.get_member(client.user.id)
	if client_member.permissions_in(message.channel).manage_messages:
		await client.delete_message(message)

async def add_x_reaction(message):
	await client.add_reaction(message, '\U0000274C') # X
	return

async def react_to_message(message, amount):
	if amount > 0:
		await client.add_reaction(message, '\U00002611') # check mark
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

