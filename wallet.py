from io import BytesIO
import json
import pycurl
import util
import db
import datetime
import settings
import asyncio

wallet = settings.wallet

logger = util.get_logger('wallet')
logger_newuser = util.get_logger('usr', log_file='user_creation.log')

def communicate_wallet(wallet_command):
	buffer = BytesIO()
	c = pycurl.Curl()
	c.setopt(c.URL, '[::1]')
	c.setopt(c.PORT, 7076)
	c.setopt(c.POSTFIELDS, json.dumps(wallet_command))
	c.setopt(c.WRITEFUNCTION, buffer.write)
	c.setopt(c.TIMEOUT, 300)
	c.perform()
	c.close()

	body = buffer.getvalue()
	parsed_json = json.loads(body.decode('iso-8859-1'))
	return parsed_json


async def create_or_fetch_user(user_id, user_name):
	logger.info('attempting to fetch user %s ...', user_id)
	user = db.get_user_by_id(user_id)
	if user is None:
		logger.info('user %s does not exist. creating new user ...',
					user_id)
		wallet_command = {'action': 'account_create', 'wallet': wallet}
		wallet_output = await asyncio.get_event_loop().run_in_executor(None, communicate_wallet, wallet_command)
		address = wallet_output['account']
		user = db.create_user(user_id=user_id, user_name=user_name,
							  wallet_address=address)
		logger.info('user %s created.', user_id)
		logger_newuser.info('user_id: %s, user_name: %s, wallet_address: %s', user_id, user_name, address)
		return user
	else:
		logger.info('user %s fetched.', user_id)
		return user


async def get_balance(user):
	user_id = user.user_id
	logger.info('getting balance for user %s', user_id)
	if user is None:
		logger.info('user %s does not exist.', user_id)
		return {'actual':0,
			'available':0,
			'pending_send':0,
			'pending':0}
	else:
		logger.info('Fetching balance from wallet for %s', user_id)
		wallet_command = {'action': 'account_balance',
				  'account': user.wallet_address}
		wallet_output = await asyncio.get_event_loop().run_in_executor(None, communicate_wallet, wallet_command)
		if 'balance' not in wallet_output:
			# Ops
			return None
		actual_balance = int(wallet_output['balance'])
		pending_balance = int(wallet_output['pending'])
		actual_balance = actual_balance / 1000000000000000000000000
		pending_balance = pending_balance / 1000000000000000000000000
		return {'actual':int(actual_balance),
			'available': int(actual_balance) - user.pending_send,
			'pending_send': user.pending_send,
			'pending':int(pending_balance) + user.pending_receive,
			}

async def make_transaction_to_address(source_user, amount, withdraw_address, uid, target_id=None, giveaway_id=0, verify_address=False):
	# Do not validate address for giveaway tx because we do not know it yet
	if verify_address:
		# Check to see if the withdraw address is valid
		wallet_command = {'action': 'validate_account_number',
				  'account': withdraw_address}
		address_validation = await asyncio.get_event_loop().run_in_executor(None, communicate_wallet, wallet_command)

		if (((withdraw_address[:4] == 'xrb_' and len(withdraw_address) != 64)
		    or (withdraw_address[:5] == 'nano_' and len(withdraw_address) != 65))
		    or address_validation['valid'] != '1'):
			raise util.TipBotException('invalid_address')

	amount = int(amount)
	if amount >= 1:
		# See if destination address belongs to a user
		if target_id is None:
			user = db.get_user_by_wallet_address(withdraw_address)
			if user is not None:
				target_id=user.user_id
		# Update pending send for user
		db.create_transaction(source_user, uid, withdraw_address,amount, target_id, giveaway_id)
		logger.info('TX queued, uid %s', uid)
	else:
		raise util.TipBotException('balance_error')

	return amount

async def make_transaction_to_user(user, amount, target_user_id, target_user_name, uid):
	target_user = await create_or_fetch_user(target_user_id, target_user_name)
	try:
		actual_tip_amount = await make_transaction_to_address(user, amount, target_user.wallet_address, uid, target_user_id)
	except util.TipBotException as e:
		return 0

	logger.info('tip queued. (from: %s, to: %s, amount: %d, uid: %s)',
				user.user_id, target_user.user_id, actual_tip_amount, uid)
	return actual_tip_amount
