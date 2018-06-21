from io import BytesIO
from celery import Celery
from celery.utils.log import get_task_logger

import redis
import json
import settings
import pycurl
import util
import db

from playhouse.shortcuts import dict_to_model

# TODO (besides test obvi)
# - receive logic

logger = get_task_logger(__name__)

r = redis.StrictRedis()
app = Celery('graham', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
app.conf.CELERY_MAX_CACHED_RESULTS = -1

def communicate_wallet(wallet_command):
	buffer = BytesIO()
	c = pycurl.Curl()
	c.setopt(c.URL, settings.node_ip)
	c.setopt(c.PORT, settings.node_port)
	c.setopt(c.POSTFIELDS, json.dumps(wallet_command))
	c.setopt(c.WRITEFUNCTION, buffer.write)
	c.setopt(c.TIMEOUT, 300)
	c.perform()
	c.close()

	body = buffer.getvalue()
	parsed_json = json.loads(body.decode('iso-8859-1'))
	return parsed_json

def account_info(account, wallet=settings.wallet):
    action = {
        "action":"account_info",
        "wallet":wallet,
        "account":account,
        "representative":"true"
    }
    return communicate_wallet(action)

def create_send_ublock(source, destination, amount, wallet=settings.wallet):
    """Returns a universal SEND block based on account and amount.
       Returns None if account has not yet been opened.
       Amount is in RAW"""
    info = account_info(source, wallet=wallet)
    if info is None:
        return None
    elif 'frontier' not in info or 'balance' not in info:
        # Either this account has not been opened or does not belong to this wallet
        return None
    # State block balance is balance after the send
    after_send = int(info['balance']) - int(amount)
    if after_send < 0:
        # This TX is invalid
        return None
    action = {
        "action":"block_create",
        "type":"state",
        "previous":info['frontier'],
        "account":source,
        "balance": after_send,
        "link":destination,
        "wallet":wallet,
        "representative":info['representative']
    }
    return communicate_wallet(action)


def process_block(block):
    """Broadcast a block to the network"""
    action = {
        "action":"process",
        "block":block
    }
    return communicate_wallet(action)

def retrieve_block(hash):
	"""Retrieves block contents by hash"""
	action = {
		"action":"block",
		"hash":hash
	}
	resp = communicate_wallet(action)
	if resp is None or 'contents' not in resp:
		return None
	return resp['contents']

@app.task(bind=True, max_retries=10)
def send_transaction(self, tx):
	"""creates a block and broadcasts it to the network, returns
	a dict if successful."""
	ret = None
	tx = dict_to_model(data=tx, model_class=db.Transaction)
	source_address = tx.source_address
	to_address = tx.to_address
	amount = tx.amount
	uid = tx.uid
	block_hash = tx.tran_id
	raw_withdraw_amt = int(amount) * util.RAW_PER_BAN if settings.banano else int(amount) * util.RAW_PER_RAI
	with redis.Redis().lock(source_address, timeout=300):
		try:
			if block_hash is not None and block_hash != '':
				sblock = create_send_ublock(source_address, to_address, raw_withdraw_amt)
				if sblock is None or 'hash' not in sblock or 'block' not in sblock:
					self.retry(countdown=2**self.request.retries)
					return None
				saved = db.Transaction.update(tran_id=sblock['hash']).where(db.Transaction.id == tx.id).execute()
				if saved == 0:
					self.retry(countdown=2**self.request.retries)
				block_hash = sblock['hash']
				processed = process_block(sblock['block'])
				if processed is None or 'hash' not in processed:
					logger.error("Couldn't process block %s, tran uid %d", sblock['hash'], tx.uid)
					self.retry(countdown=2**self.request.retries)
					return None
			else:
				block = retrieve_block(block_hash)
				if block is None:
					logger.error("Already had saved block hash for TX UID %s, failed to retrieve", tx.uid)
					self.retry(countdown=2**self.request.retries)
					return None
				logger.info("Already have block hash, re-processing block")
				processed = process_block(block)
				if processed is None or 'hash' not in processed:
					logger.error("Couldn't process block %s, tran uid %d", block_hash, tx.uid)
					self.retry(countdown=2**self.request.retries)
					return None
		except pycurl.error:
			self.retry(countdown=2**self.request.retries)
			return None
		except Exception as e:
			logger.exception(e)
			self.retry(countdown=2**self.request.retries)
			return None
	ret = json.dumps({"success": {"source":source_address, "txid":block_hash, "uid":uid, "destination":to_address, "amount":amount}})
	r.rpush('/tx_completed', ret)
	target_user = db.get_user_by_wallet_address(to_address)
	if target_user is not None:
		pocket_tx(to_address, block_hash)
	return ret

def pocket_tx(account, block):
	with redis.Redis().lock(account, timeout=300):
		action = {
			"action":"receive",
			"wallet":settings.wallet,
			"account":account,
			"block":block
		}
		return communicate_wallet(action)
	return None

@app.task
def pocket_task(accounts):
	"""Poll pending transactions in accounts and pocket them"""
	processed_count = 0
	# The lock ensures we don't enter this function twice
	# It wouldn't hurt anything, but there's really no point to do so
	have_lock = False
	lock = redis.Redis().lock("POCKET_TASK", timeout=300)
	try:
		have_lock = lock.acquire(blocking=False)
		if not have_lock:
			logger.info("Could not acquire lock for POCKET_TASK")
			return None
		accts_pending_action = {
			"action":"accounts_pending",
			"accounts":accounts,
			"threshold":util.RAW_PER_BAN if settings.banano else util.RAW_PER_RAI,
			"count":5
		}
		resp = communicate_wallet(accts_pending_action)
		if resp is None or 'blocks' not in resp:
			return None
		for account, blocks in resp['blocks'].items():
			for b in blocks:
				logger.info("Receiving block %s for account %s", b, account)
				rcv_resp = pocket_tx(account, b)
				if rcv_resp is None or 'block' not in rcv_resp:
					logger.info("Couldn't receive %s - response: %s", b, str(rcv_resp))
				else:
					processed_count += 1
					logger.info("pocketed block %s", b)
		return processed_count
	except Exception as e:
		logger.exception(e)
		return None
	finally:
		if have_lock:
			lock.release()

if __name__ == '__main__':
	app.start()
