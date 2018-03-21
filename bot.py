import collections
import random
import re
import errno
from socket import error as socket_error
import discord
import asyncio

import wallet
import util
import settings
import db

logger = util.get_logger("main")

AT_BOT = "<@" + settings.discord_bot_id + ">"

BOT_VERSION = "0.1"

logger.info("started.")
client = discord.Client()

BotFeature = collections.namedtuple('BotFeature', ['command', 'command_keywords', 'response_templates'])

general_responses = {
    "command_not_found":
	[
	    "I didn't understand that, try !help"
	]
}


def setup_bot():
    help_feature = BotFeature(command="HELP",
			      command_keywords=["!help", "!man"],
			      response_templates=
			      {"success": [
				  "NanoTipBot v%s - An open source NANO tip bot for Discord \n" +
						  "Developed by <@303599885800964097> - feel free to contribute and provide feedback \n" +
						  "\n" +
						  "Supported commands are:" + 
				  "\n" +
				  ":small_blue_diamond: !help !man \n\n" +
				  "    Show this message. \n"
				  "\n" +
				  ":small_blue_diamond: !balance \n\n" +
				  "    Check the balance of your tip account \n" +
				  "\n" +
				  ":small_blue_diamond: !deposit !register \n\n" +
				  "    Gives you your tip bot address (with QR code) \n" +
				  "\n" +
				  ":small_blue_diamond: !tip \n" +
				  ":small_blue_diamond: needs: amount who \n" +
				  ":small_blue_diamond: ex: !tip 1000 @bbedward\n\n" +
				  "    Tip other users. You have to mention who you want to tip and tell me the amount. " +
				  "    If the operation is successful, the other users will be informed of your action. \n" +
				  "    Note that tip units are in 1/1000000th of a nano. \n" +
				  "    e.g. 1xrb = 0.000001 NANO. \n" + 
				  "\n" +
				  ":small_blue_diamond: !withdraw \n" +
				  ":small_blue_diamond: needs: address \n\n" +
				  "    Withdraw all of your coins to your wallet. You have to supply an " +
				  "address for this. \n" +
				  "\n" +
				  ":small_blue_diamond: !toptips \n\n" +
				  "    Show who has tipped the most. \n\n\n" +
				  "NANO Tip Bot is open source: https://github.com/bbedward/NANO-Tip-Bot"
			      ]})

    balance_feature = BotFeature(command="BALANCE",
				 command_keywords=["!balance"],
				 response_templates=
				 {"success": [
				     "Balance: %d xrb",
				     "You have %d xrb",
				     "You've got %d xrb"
				 ]})

    deposit_feature = BotFeature(command="DEPOSIT",
				 command_keywords=["!deposit", "!register"],
				 response_templates=
				 {"success": [
				     "Your wallet address is %s. \n QR: %s"
				 ]})

    tip_feature = BotFeature(command="TIP",
			     command_keywords=["!tip"],
			     response_templates=
			     {"amount_not_found": [
				 "I couldn't find the amount in your message!"
			     ], "insufficient_funds": [
				 "You don't have enough coins to tip that much!"
			     ], "error": [
				 "Something went wrong with the tip. I wrote to logs. "
			     ], "tip_received": [
				 "You were tipped %d xrb by <@%s> ! "
			     ]})

    withdraw_feature = BotFeature(command="WITHDRAW",
				  command_keywords=["!withdraw"],
				  response_templates=
				  {"success": [
				      "TXID: %s"
				  ], "address_not_found": [
				      "I did not see a destination address in your message, try !help"
				  ], "invalid_address": [
						      "Withdraw address is not valid"
						  ], "error": [
				      "Something went wrong ! :thermometer_face: "
				  ]})

    top_feature = BotFeature(command="TOP",
			     command_keywords=["!toptips"],
			     response_templates=
			     {"header": [
				 "Tip Leaderboard :point_down:"
			     ], "empty": [
				 "The leaderboard is empty!"
			     ]})

    return [help_feature, balance_feature, deposit_feature, tip_feature, withdraw_feature, top_feature]

bot_features = setup_bot()

async def handle_message(features, message):
	feat = features[0]

	# Ignore messages from users that are < 1 second apart (prevent spam)
	if db.last_msg_check(message.author.id) == False:
		return

	if feat.command == "HELP" and message.channel.is_private:
		post_response(message, feat.response_templates["success"], BOT_VERSION)

	elif feat.command == "BALANCE" and message.channel.is_private:
		balance = wallet.get_balance(message.author.id)
		post_response(message, feat.response_templates["success"], balance)

	elif feat.command == "DEPOSIT" and message.channel.is_private:
		user_deposit_address = wallet.create_or_fetch_user(message.author.id, message.author.name).wallet_address
		post_response(message, feat.response_templates["success"], user_deposit_address,
			      get_qr_url(user_deposit_address))

	elif feat.command == "WITHDRAW" and message.channel.is_private:
		try:
			withdraw_address = find_address(message.content)
			source_address = wallet.get_address(message.author.id)
			amount = wallet.get_balance(message.author.id)
			if amount == 0:
				post_response(message, feat.response_templates["invalid_amt"]);
			else:
				txid = wallet.make_transaction_to_address(source_address, amount, withdraw_address)
				post_response(message, feat.response_templates["success"], txid)
		except util.TipBotException as e:
			if e.error_type == "address_not_found":
				post_response(message, feat.response_templates["address_not_found"])
				if e.error_type == "invalid_address":
				    post_response(message, feat.response_templates["invalid_address"])
			if e.error_type == "error":
				post_response(message, feat.response_templates["error"])

	elif feat.command == "TIP":
		try:
			amount = find_amount(message.content)
			# Make sure user has specified at least 1 recipient
			if len(message.mentions) < 1:
				return
			# Make sure this user has enough in their balance to complete this tip
			required_amt = amount * len(message.mentions)
			user_balance = wallet.get_balance(message.author.id)
			if user_balance < required_amt:
				asyncio.get_event_loop().create_task(post_dm(message.author.id, feat.response_templates["insufficient_funds"]))
				return
			# Distribute tips
			for member in message.mentions:
				# Do not send tips to exempt parties (such as bots), subtract these from totals for reactions
				if member.id in settings.exempt_users:
					required_amt-=amount
				else:
					wallet.make_transaction_to_user(message.author.id, amount, member.id, member.name)
					asyncio.get_event_loop().create_task(
						post_dm(member.id, feat.response_templates["tip_received"], amount, message.author.id))
			asyncio.get_event_loop().create_task(react_to_message(message, required_amt))
		except util.TipBotException as e:
			if e.error_type == "amount_not_found":
				asyncio.get_event_loop().create_task(post_dm(message.author.id, feat.response_templates["amount_not_found"]))
			if e.error_type == "error":
				post_response(message, feat.response_templates["error"])

	elif feat.command == "TOP":
		top_users = wallet.get_top_users()
		if len(top_users) == 0:
			post_response(message, feat.response_templates["empty"])
		else:
			response = random.choice(feat.response_templates["header"]) + "\n"
			for top_user in top_users:
				response += '\n %d: %.6f nano tipped by %s' % (top_user['index'],
							     top_user['amount'], top_user['name'])
			post_response(message, [response])

def get_qr_url(text):
	return 'https://chart.googleapis.com/chart?cht=qr&chl=%s&chs=180x180&choe=UTF-8&chld=L|2' % text

def find_address(input_text):
	address = input_text.split(' ')[1]
	if address is None:
		raise util.TipBotException("invalid_address")
	return address

def find_amount(input_text):
	regex = r'(?:^|\s)(\d*\.?\d+)(?=$|\s)'
	matches = re.findall(regex, input_text, re.IGNORECASE)
	if len(matches) == 1:
		return float(matches[0].strip())
	else:
		raise util.TipBotException("amount_not_found")

def post_response(message, response_list, *args):
	response = random.choice(response_list) % tuple(args)
	if not message.channel.is_private:
		response = "<@" + message.author.id + "> " + response
	logger.info("sending response: '%s' to message: %s", response, message.content)
	asyncio.get_event_loop().create_task(client.send_message(message.channel, response))


@client.event
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

@client.event
async def post_dm(user_id, text_list, *args):
	text = random.choice(text_list) % tuple(args)
	logger.info("sending dm: '%s' to user: %s", text, user_id)
	await client.send_message(await client.get_user_info(user_id), text)

@client.event
async def on_ready():
	logger.info('connected as %s and id %s', client.user.name, client.user.id)

@client.event
async def on_message(message):
	features = [f for f in bot_features for c in f.command_keywords if c in message.content]
	if len(features) == 1:
		await handle_message(features, message)


client.run(settings.discord_bot_token)

