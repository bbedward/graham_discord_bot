from io import BytesIO
from celery import Celery
from celery.utils.log import get_task_logger

import json
import settings
import pycurl

#from db import inc_tx_attempts, get_user_by_wallet_address, mark_transaction_processed

# TODO (besides test obvi)
# - receive logic
# - callback to notify users of withdraw

MAX_TX_RETRIES = 3
DONATION_ADDRESS = '1234'

logger = get_task_logger(__name__)

app = Celery('graham', broker='pyamqp://guest@localhost//')

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

@app.task(bind=True)
def send_transaction(self, tx):
    try:
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
        logger.debug("RPC Send")
        wallet_output = communicate_wallet(wallet_command)
        logger.debug("RPC Response")
        if 'block' in wallet_output:
            txid = wallet_output['block']
            mark_tx_processed(source_address, txid, uid, to_address, amount)
            return
        else:
            # Not sure what happen but we'll retry a few times
            if attempts >= MAX_TX_RETRIES:
                logger.info("Max Retires Exceeded for TX UID: %s", uid)
                mark_tx_processed(source_address, 'invalid', uid, to_address, amount)
            else:
                db.inc_tx_attempts(uid)
                self.retry()
    except pycurl.error:
        if uid is not None:
            db.inc_tx_attempts(uid)
            self.retry()
    except Exception as e:
        logger.exception(e)

# TODO this should b non-blocking, whether thats a callback or subtask isk
def mark_tx_processed(source_address, block, uid, to_address, amount):
	src_usr = db.get_user_by_wallet_address(source_address)
	trg_usr = db.get_user_by_wallet_address(to_address)
	source_id=None
	target_id=None
	pending_delta = int(amount) * -1
	if src_usr is not None:
		source_id=src_usr.user_id
	if trg_usr is not None:
		target_id=trg_usr.user_id
	db.mark_transaction_processed(uid, pending_delta, source_id, block, target_id)
	logger.info('TX processed. UID: %s, HASH: %s', uid, block)
	if target_id is None and to_address != DONATION_ADDRESS and block != 'invalid':
		pass
	# TODO callback to notify user of withdraw

if __name__ == '__main__':
	app.start()
