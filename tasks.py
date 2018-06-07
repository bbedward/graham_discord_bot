from io import BytesIO
from celery import Celery
from celery.utils.log import get_task_logger

import redis
import json
import settings
import pycurl

# TODO (besides test obvi)
# - receive logic

MAX_TX_RETRIES = 3

logger = get_task_logger(__name__)

r = redis.StrictRedis()
app = Celery('graham', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
app.conf.CELERY_MAX_CACHED_RESULTS = -1

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
            r.rpush('send_finished', self.request.id)
            return {"success": {"source":source_address, "txid":txid, "uid":uid, "destination":to_address, "amount":amount}}
#        else:
#            # Not sure what happen but we'll retry a few times
#            if attempts >= MAX_TX_RETRIES:
#                logger.info("Max Retires Exceeded for TX UID: %s", uid)
#                mark_tx_processed(source_address, 'invalid', uid, to_address, amount)
#            else:
#                db.inc_tx_attempts(uid)
#                self.retry()
    except pycurl.error:
        if uid is not None:
            self.retry()
    except Exception as e:
        logger.exception(e)

if __name__ == '__main__':
	app.start()
