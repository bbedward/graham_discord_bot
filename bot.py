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
import paginator

logger = util.get_logger("main")

BOT_VERSION = "1.8.5"

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
AUTHOR_HEADER="NANO Tip Bot v%s" % BOT_VERSION
BALANCE_CMD="%sbalance" % COMMAND_PREFIX
BALANCE_OVERVIEW="Display balance of your account"
BALANCE_INFO=("Displays the balance of your tip account (in naneroo) as described:" +
		"\nActual Balance: The actual balance in your tip account" +
		"\nAvailable Balance: The balance you are able to tip with (Actual - Pending Send)" +
		"\nPending Send: Tips you have sent, but have not yet been broadcasted to network" +
		"\nPending Receipt: Tips that have been sent to you, but have not yet been pocketed by the node. " +
		"\nPending funds will be available for tip/withdraw after the transactions have been processed")
DEPOSIT_CMD="%sdeposit or %sregister" % (COMMAND_PREFIX, COMMAND_PREFIX)
DEPOSIT_OVERVIEW="Shows your account address"
DEPOSIT_INFO=("Displays your tip bot account address along with a QR code" +
		"\n- Send NANO to this address to increase your tip bot balance" +
		"\n- If you do not have a tip bot account yet, this command will create one for you (receiving a tip automatically creates an account too)")
WITHDRAW_CMD="%swithdraw <address> <(optional) amount>" % COMMAND_PREFIX
WITHDRAW_OVERVIEW="Allows you to withdraw from your tip account"
WITHDRAW_INFO="Withdraws specified amount to specified address, if amount isn't specified your entire tip account balance will be withdrawn"
TIP_CMD="%stip <amount> <*users>" % COMMAND_PREFIX
TIP_OVERVIEW="Send a tip to mentioned users"
TIP_INFO=("Tip specified amount to mentioned user(s) (minimum tip is 1 naneroo)" +
		"\nTip units are in 1 millionth of NANO. 1 naneroo = 0.000001 NANO" +
		"\nThe recipient(s) will be notified of your tip via private message" +
		"\nSuccessful tips will be deducted from your available balance immediately")
TIPSPLIT_CMD="%stipsplit <amount> <*users>" % COMMAND_PREFIX
TIPSPLIT_OVERVIEW="Split a tip among mentioned uses"
TIPSPLIT_INFO="`Distribute <amount> evenly to all mentioned users"
RAIN_CMD="%srain <amount>" % COMMAND_PREFIX
RAIN_OVERVIEW="Split tip among all active* users"
RAIN_INFO=("Distribute <amount> evenly to users who are eligible." +
		"\nTo receive rain you must:" +
		"\n- Have used this tip bot before" +
		"\n- Must be online and have been actively contributing around the time a rain occurs" +
		"\nNote: Spamming messages in a short period of time does not make you rain eligible" +
		"\nMinimum rain amount: %d naneroo") % (RAIN_MINIMUM)
START_GIVEAWAY_CMD="%sgivearai or %ssponsorgiveaway <amount> <entry_fee>" % (COMMAND_PREFIX, COMMAND_PREFIX)
START_GIVEAWAY_OVERVIEW="Sponsor a giveaway"
START_GIVEAWAY_INFO=("Start a giveaway with given amount and entry fee (in naneroo)." +
		"\nEntry costs are added to the total prize pool" +
		"\nGiveaway will end and choose random winner after 60 minutes" +
		"\nMinimum required to sponsor a giveaway: %d naneroo") % (GIVEAWAY_MINIMUM)
ENTER_CMD="%sticket <(fee)>" % COMMAND_PREFIX
ENTER_OVERVIEW="Enter the currently active giveaway"
ENTER_INFO=("Enter the current giveaway, if there is one. Takes (fee) as argument if there's an entry fee")
TIPGIVEAWAY_CMD="%stipgiveaway or %sdonate <amount>" % (COMMAND_PREFIX, COMMAND_PREFIX)
TIPGIVEAWAY_OVERVIEW="Add to present or future giveaway prize pool"
TIPGIVEAWAY_INFO="Add <amount> to the current giveaway pool\nIf there is no giveaway, one will be started when minimum is reached.\nTips >= %d naneroo automatically enter you for giveaways sponsored by the community (Not for giveaways sponsored by individuals)" % (TIPGIVEAWAY_AUTO_ENTRY)
TICKETSTATUS_CMD="%sticketstatus" % COMMAND_PREFIX
TICKETSTATUS_OVERVIEW="Check if you are entered into the current giveaway"
TICKETSTATUS_INFO=TICKETSTATUS_OVERVIEW
GIVEAWAY_STATS_CMD="%sgiveawaystats or %sgoldenticket" % (COMMAND_PREFIX, COMMAND_PREFIX)
GIVEAWAY_STATS_OVERVIEW="Display statistics relevant to the current giveaway"
GIVEAWAY_STATS_INFO=GIVEAWAY_STATS_OVERVIEW
WINNERS_CMD="%swinners" % COMMAND_PREFIX
WINNERS_INFO="`Display previous giveaway winners"
WINNERS_OVERVIEW=WINNERS_INFO
LEADERBOARD_CMD="%sleaderboard or %sballers" % (COMMAND_PREFIX, COMMAND_PREFIX)
LEADERBOARD_INFO="Display the all-time tip leaderboard"
LEADERBOARD_OVERVIEW=LEADERBOARD_INFO
TOPTIPS_CMD="%stoptips" % COMMAND_PREFIX
TOPTIPS_OVERVIEW="Display largest individual tips"
TOPTIPS_INFO="Display the single largest tips for the past 24 hours, current month, and all time"
STATS_CMD="%stipstats" % COMMAND_PREFIX
STATS_OVERVIEW="Display your personal tipping stats"
STATS_INFO="Display your personal tipping stats (rank, total tipped, and average tip)"
SETTIP_INFO=("%ssettiptotal <user>:\n Manually set the 'total tipped' for a user (for tip leaderboard)" +
		"\n This command is role restricted and only available to users with certain roles (e.g. Moderators)") % COMMAND_PREFIX
SETCOUNT_INFO=("%ssettipcount <user>:\n Manually set the 'tip count' for a user (for average tip statistic)" +
		"\n This command is role restricted and only available to users with certain roles (e.g. Moderators)") % COMMAND_PREFIX
BOT_DESCRIPTION=("NanoTipBot v%s - An open source NANO tip bot for Discord\n" +
		"Developed by bbedward - Feel free to send suggestions, ideas, and/or tips\n") % BOT_VERSION
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
TIPSPLIT_SMALL="Tip amount is too small to be distributed to that many users"
RAIN_NOBODY="I couldn't find anybody eligible to receive rain"
GIVEAWAY_EXISTS="There's already an active giveaway"
GIVEAWAY_STARTED="%s has sponsored a giveaway of %.6f NANO! Use:\n - `" + COMMAND_PREFIX + "ticket` to enter\n - `" + COMMAND_PREFIX + "donate` to increase the pot\n - `" + COMMAND_PREFIX + "ticketstatus` to check the status of your entry"
GIVEAWAY_STARTED_FEE="%s has sponsored a giveaway of %.6f NANO! The entry fee is %d naneroo. Use:\n - `" + COMMAND_PREFIX + "ticket %d` to buy your ticket\n - `" + COMMAND_PREFIX + "donate` to increase the pot\n - `" + COMMAND_PREFIX + "ticketstatus` to check the status of your entry"
GIVEAWAY_MAX_FEE="Giveaway entry fee cannot be more than 5% of the prize pool"
GIVEAWAY_ENDED="Congratulations! <@%s> was the winner of the giveaway! They have been sent %.6f NANO!"
GIVEAWAY_STATS="There are %d entries to win %.6f NANO ending in %s - sponsored by %s.\nUse:\n - `" + COMMAND_PREFIX + "ticket` to enter\n -`" + COMMAND_PREFIX + "donate` to add to the pot\n - `" + COMMAND_PREFIX + "ticketstatus` to check status of your entry"
GIVEAWAY_STATS_FEE="There are %d entries to win %.6f NANO ending in %s - sponsored by %s.\nEntry fee: %d naneroo. Use:\n - `" + COMMAND_PREFIX + "ticket %d` to enter\n - `" + COMMAND_PREFIX + "donate` to add to the pot\n - `" + COMMAND_PREFIX + "ticketstatus` to check the status of your entry"
GIVEAWAY_STATS_INACTIVE="There are no active giveaways\n%d naneroo required to to automatically start one! Donate to the pot using `" + COMMAND_PREFIX + "donate`. You can also sponsor one using `" + COMMAND_PREFIX + "givearai`"
ENTER_ADDED="You've been successfully entered into the giveaway"
ENTER_DUP="You've already entered the giveaway"
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
client = Bot(command_prefix=COMMAND_PREFIX,description=BOT_DESCRIPTION)
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

def is_admin(user):
	return (has_admin_role(user.roles) or user.id in settings.admin_ids)

### Commands
def build_help(page):
	if page == 0:
		entries = []
		entries.append(paginator.Entry(BALANCE_CMD,BALANCE_OVERVIEW))
		entries.append(paginator.Entry(DEPOSIT_CMD,DEPOSIT_OVERVIEW))
		entries.append(paginator.Entry(WITHDRAW_CMD,WITHDRAW_OVERVIEW))
		entries.append(paginator.Entry(TIP_CMD,TIP_OVERVIEW))
		entries.append(paginator.Entry(TIPSPLIT_CMD,TIPSPLIT_OVERVIEW))
		entries.append(paginator.Entry(RAIN_CMD,RAIN_OVERVIEW))
		entries.append(paginator.Entry(START_GIVEAWAY_CMD,START_GIVEAWAY_OVERVIEW))
		entries.append(paginator.Entry(ENTER_CMD,ENTER_OVERVIEW))
		entries.append(paginator.Entry(TIPGIVEAWAY_CMD,TIPGIVEAWAY_OVERVIEW))
		entries.append(paginator.Entry(TICKETSTATUS_CMD,TICKETSTATUS_OVERVIEW))
		entries.append(paginator.Entry(GIVEAWAY_STATS_CMD,GIVEAWAY_STATS_OVERVIEW))
		entries.append(paginator.Entry(WINNERS_CMD,WINNERS_OVERVIEW))
		entries.append(paginator.Entry(LEADERBOARD_CMD,LEADERBOARD_OVERVIEW))
		entries.append(paginator.Entry(TOPTIPS_CMD,TOPTIPS_OVERVIEW))
		entries.append(paginator.Entry(STATS_CMD,STATS_OVERVIEW))
		author=AUTHOR_HEADER
		title="Command Overview"
		return paginator.Page(entries, title=title,author=author)
	elif page == 1:
		entries = []
		entries.append(paginator.Entry(BALANCE_CMD,BALANCE_INFO))
		entries.append(paginator.Entry(DEPOSIT_CMD,DEPOSIT_INFO))
		entries.append(paginator.Entry(WITHDRAW_CMD,WITHDRAW_INFO))
		author="Account Commands"
		description="Check accont balance, withdraw, or deposit"
		return paginator.Page(entries, author=author,description=description)
	elif page == 2:
		entries = []
		entries.append(paginator.Entry(TIP_CMD,TIP_INFO))
		entries.append(paginator.Entry(TIPSPLIT_CMD,TIPSPLIT_INFO))
		entries.append(paginator.Entry(RAIN_CMD,RAIN_INFO))
		author="Tipping Commands"
		description="The different ways you are able to tip with this bot"
		return paginator.Page(entries, author=author,description=description)
	elif page == 3:
		entries = []
		entries.append(paginator.Entry(START_GIVEAWAY_CMD,START_GIVEAWAY_INFO))
		entries.append(paginator.Entry(ENTER_CMD,ENTER_INFO))
		entries.append(paginator.Entry(TIPGIVEAWAY_CMD,TIPGIVEAWAY_INFO))
		entries.append(paginator.Entry(TICKETSTATUS_CMD,TICKETSTATUS_INFO))
		author="Giveaway Commands"
		description="The different ways to interact with the bot's giveaway functionality"
		return paginator.Page(entries, author=author, description=description)
	elif page == 4:
		entries = []
		entries.append(paginator.Entry(GIVEAWAY_STATS_CMD,GIVEAWAY_STATS_INFO))
		entries.append(paginator.Entry(WINNERS_CMD,WINNERS_INFO))
		entries.append(paginator.Entry(LEADERBOARD_CMD,LEADERBOARD_INFO))
		entries.append(paginator.Entry(TOPTIPS_CMD,TOPTIPS_INFO))
		entries.append(paginator.Entry(STATS_CMD,STATS_INFO))
		author="Statistics Commands"
		description="Individual, bot-wide, and giveaway stats"
		return paginator.Page(entries, author=author,description=description)
	elif page == 5:
		entries = []
		author=AUTHOR_HEADER + " - by bbedward"
		description=("**Reviews**:\n" + "'10/10 True Masterpiece' - NANO Core Team" +
				"\n'0/10 Didn't get rain' - Almost everybody else\n\n" +
				"NANO Tip Bot is completely free to use and open source." +
				" Developed by bbedward (reddit: /u/bbedward, discord: bbedward#9246)" +
				"\n Feel free to send tips, suggestions, and feedback. (don't harass me too much plz\n\n" +
				"github: https://github.com/bbedward/NANO-Tip-Bot")
		return paginator.Page(entries, author=author,description=description)

@client.command(pass_context=True)
async def help(ctx):
	message = ctx.message
	pages=[]
	pages.append(build_help(0))
	pages.append(build_help(1))
	pages.append(build_help(2))
	pages.append(build_help(3))
	pages.append(build_help(4))
	pages.append(build_help(5))
	try:
		pages = paginator.Paginator(client, message=message, page_list=pages,as_dm=True)
		await pages.paginate(start_page=1)
	except paginator.CannotPaginate as e:
		logger.exception(str(e))

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
			await post_usage(message, TIP_CMD, TIP_INFO)
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
			await post_usage(message, TIPSPLIT_CMD, TIPSPLIT_INFO)
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
			await post_usage(message, RAIN_CMD, RAIN_INFO)
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
			await post_usage(message, START_GIVEAWAY_CMD, START_GIVEAWAY_INFO)

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
		if contributions >= fee and not db.is_banned(message.author.id):
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
				await post_usage(message, ENTER_CMD, ENTER_INFO)
			else:
				await post_usage(message, TIPGIVEAWAY_CMD, TIPGIVEAWAY_INFO)

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

@client.command(pass_context=True, aliases=['bigtippers', 'ballers'])
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

async def post_usage(message, command, description):
	embed = discord.Embed(colour=discord.Colour.purple())
	embed.title = "Usage:"
	embed.add_field(name=command, value=description,inline=False)
	await client.send_message(message.author, embed=embed)

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
	if message.channel.is_private:
		return
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

