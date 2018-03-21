from io import BytesIO
import json
import pycurl
import util
import db
import datetime
import settings

TOP_USERS_COUNT = 15

wallet = settings.wallet

logger = util.get_logger('wallet')


def communicate_wallet(wallet_command):
    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, '[::1]')
    c.setopt(c.PORT, 7076)
    c.setopt(c.POSTFIELDS, json.dumps(wallet_command))
    c.setopt(c.WRITEFUNCTION, buffer.write)
    c.perform()
    c.close()

    body = buffer.getvalue()
    parsed_json = json.loads(body.decode('iso-8859-1'))
    return parsed_json


def create_or_fetch_user(user_id, user_name):
    logger.info('attempting to fetch user %s ...', user_id)
    user = db.get_user_by_id(user_id)
    if user is None:
        logger.info('user %s does not exist. creating new user ...',
                    user_id)
        wallet_command = {'action': 'account_create', 'wallet': wallet}
        wallet_output = communicate_wallet(wallet_command)
        address = wallet_output['account']
        user = db.create_user(user_id=user_id, user_name=user_name,
                              wallet_address=address)
        logger.info('user %s created.', user_id)
        return user
    else:
        logger.info('user %s fetched.', user_id)
        return user


def get_balance(user_id):
    logger.info('getting balance for user %s', user_id)
    user = db.get_user_by_id(user_id)
    if user is None:
        logger.info('user %s does not exist.', user_id)
        return 0.0
    else:
        logger.info('Fetching balance from wallet for %s', user_id)
        wallet_command = {'action': 'account_balance',
                          'account': user.wallet_address}
        wallet_output = communicate_wallet(wallet_command)
        wallet_command = {'action': 'rai_from_raw',
                          'amount': int(wallet_output['balance'])}
        balance = communicate_wallet(wallet_command)
        return int(balance['amount'])


def get_address(user_id):
    logger.info('getting wallet address for user %s ...', user_id)
    user = db.get_user_by_id(user_id)
    if user is None:
        return None
    else:
        return user.wallet_address


def make_transaction_to_address(source_address, amount,
                                withdraw_address, uid):

    # Check to see if the withdraw address is valid

    wallet_command = {'action': 'validate_account_number',
                      'account': withdraw_address}
    address_validation = communicate_wallet(wallet_command)

    # If the address was the incorrect length, did not start with xrb_ or nano_ or was deemed invalid by the node, return an error.

    address_prefix_valid = withdraw_address[:4] == 'xrb_' \
        or withdraw_address[:5] == 'nano_'
    if len(withdraw_address) != 64 or not address_prefix_valid \
        or address_validation['valid'] != '1':
        raise util.TipBotException('invalid_address')

    raw_withdraw_amount = str(int(amount)) + '000000000000000000000000'

    wallet_command = {
        'action': 'send',
        'wallet': wallet,
        'source': source_address,
        'destination': withdraw_address,
        'amount': int(raw_withdraw_amount),
	'id': uid
        }
    wallet_output = communicate_wallet(wallet_command)
    logger.info('Withdraw successful')
    return wallet_output['block']


def get_top_users():
    return db.get_top_users(TOP_USERS_COUNT)


def make_transaction_to_user(
    user_id,
    amount,
    target_user_id,
    target_user_name,
    uid
    ):
    target_user = create_or_fetch_user(target_user_id, target_user_name)
    user = db.get_user_by_id(user_id)
    txid = make_transaction_to_address(user.wallet_address, amount,
                                target_user.wallet_address, uid)
    db.update_tipped_amt(user_id, amount)
    logger.info('tip successful. (from: %s, to: %s, amount: %d, txid: %s)',
                user_id, target_user.user_id, amount, txid)
    return txid;
