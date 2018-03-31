import datetime
import util
from peewee import *
from playhouse.sqliteq import SqliteQueueDatabase

# (Seconds) how long a user must wait in between messaging the bot
LAST_MSG_TIME = 1

db = SqliteQueueDatabase('nanotipbot.db')

logger = util.get_logger("db")

### User Stuff
def get_user_by_id(user_id):
	try:
		user = User.get(user_id=user_id)
		return user
	except User.DoesNotExist:
		# logger.debug('user %s does not exist !', user_id)
		return None

def get_user_by_wallet_address(address):
	try:
		user = User.get(wallet_address=address)
		return user
	except User.DoesNotExist:
		# logger.debug('wallet %s does not exist !', address)
		return None

def get_active_users(since_minutes):
	since_ts = datetime.datetime.now() - datetime.timedelta(minutes=since_minutes)
	users = User.select(User.user_id).where(User.last_msg > since_ts)
	return_ids = []
	for user in users:
		return_ids.append(user.user_id)
	return return_ids

def get_address(user_id):
	logger.info('getting wallet address for user %s ...', user_id)
	user = get_user_by_id(user_id)
	if user is None:
		return None
	else:
		return user.wallet_address

def get_top_users(count):
	users = User.select().where(User.tipped_amount > 0).order_by(User.tipped_amount.desc()).limit(count)
	return_data = []
	for idx, user in enumerate(users):
		return_data.append({'index': idx + 1, 'name': user.user_name, 'amount': user.tipped_amount})
	return return_data

def get_tip_stats(user_id):
	try:
		user = get_user_by_id(user_id)
		rank = User.select().where(User.tipped_amount > user.tipped_amount).count() + 1
		if user.tip_count == 0:
			average = 0
		else:
			average = user.tipped_amount / user.tip_count
		return {'rank':rank, 'total':user.tipped_amount, 'average':average,'top':float(user.top_tip) / 1000000}
	except User.DoesNotExist:
		return None

def update_tip_total(user_id, new_total):
	user = get_user_by_id(user_id)
	if user is None:
		return
	user.tipped_amount = new_total
	user.save()
	return

def update_tip_count(user_id, new_count):
	user = get_user_by_id(user_id)
	if user is None:
		return
	user.tip_count = new_count
	user.save()
	return

def update_top_tip(user_id, tip):
	user = get_user_by_id(user_id)
	if user is None:
		return
	if int(float(user.top_tip)) > int(tip):
		return
	user.top_tip=tip
	user.top_tip_ts=datetime.datetime.now()
	user.save()
	return

def update_pending(user_id, send=0, receive=0):
	user = get_user_by_id(user_id)
	if user is None:
		return False
	user.pending_send += send
	user.pending_receive += receive
	user.save()
	return True

def create_user(user_id, user_name, wallet_address):
	user = User(user_id=user_id,
		    user_name=user_name,
		    wallet_address=wallet_address,
		    tipped_amount=0.0,
		    wallet_balance=0.0,
		    pending_receive=0.0,
		    pending_send=0.0,
		    tip_count=0,
		    created=datetime.datetime.now(),
		    last_msg=datetime.datetime.now(),
		    top_tip='0',
		    top_tip_ts=datetime.datetime.now()
		    )
	user.save()
	return user

### Transaction Stuff
def create_transaction(uuid, source_addr, to_addr, amt, source_id, target_id=None, giveaway_id=0):
	tx = Transaction(uid=uuid,
			 source_address=source_addr,
			 to_address=to_addr,
			 amount=amt,
			 processed=False,
			 created=datetime.datetime.now(),
			 tran_id='',
			 attempts=0,
			 giveawayid=giveaway_id
			)
	tx.save()
	update_pending(source_id, send=amt)
	if target_id is not None:
		update_pending(target_id, receive=amt)
	return tx

def get_unprocessed_transactions():
	# We don't simply return the txs list cuz that causes issues with database locks in the thread
	txs = Transaction.select().where((Transaction.processed == False) & (Transaction.giveawayid == 0)).order_by(Transaction.created)
	return_data = []
	for tx in txs:
		return_data.append({'uid':tx.uid,'source_address':tx.source_address,'to_address':tx.to_address,'amount':tx.amount,'attempts':tx.attempts})
	return return_data

def process_giveaway_transactions(giveaway_id, winner_user_id):
	txs = Transaction.select().where(Transaction.giveawayid == giveaway_id)
	winner = get_user_by_id(winner_user_id);
	pending_receive = 0
	for tx in txs:
		tx.to_address = winner.wallet_address
		tx.giveawayid = 0
		pending_receive += int(tx.amount)
		tx.save()
	update_pending(winner_user_id, receive=pending_receive)

# Start Giveaway
def start_giveaway(user_id, user_name, amount, end_time, channel):
	giveaway = Giveaway(started_by=user_id,
			    started_by_name=user_name,
			    active=True,
			    amount = amount,
			    tip_amount = 0,
			    end_time=end_time,
			    channel_id = channel,
			    winner_id = None
			   )
	giveaway.save()
	tip_amt = update_giveaway_transactions(giveaway.id)
	giveaway.tip_amount = tip_amt
	giveaway.save()
	return giveaway

def update_giveaway_transactions(giveawayid):
	tip_sum = 0
	txs = Transaction.select().where(Transaction.giveawayid == -1)
	for tx in txs:
		tx.giveawayid = giveawayid
		tip_sum += int(tx.amount)
		tx.save()

	return float(tip_sum)/ 1000000

def get_giveaway():
	try:
		giveaway = Giveaway.get(active=True)
		return giveaway
	except:
		return None

def add_tip_to_giveaway(amount):
	giveaway = get_giveaway()
	if giveaway is not None:
		giveaway.tip_amount += amount
		giveaway.save()

def get_tipgiveaway_sum():
	tip_sum = 0
	txs = Transaction.select().where(Transaction.giveawayid == -1)
	for tx in txs:
		tip_sum += int(tx.amount)
	return tip_sum

# Get tipgiveaway contributions
def get_tipgiveaway_contributions(user_id):
	tip_sum = 0
	user = get_user_by_id(user_id)
	txs = Transaction.select().where((Transaction.giveawayid == -1) & (Transaction.source_address == user.wallet_address))
	for tx in txs:
		tip_sum += int(tx.amount)
	return tip_sum

# Returns winning user
def finish_giveaway():
	picker_query = Contestant.select().order_by(fn.Random())
	winner = get_user_by_id(picker_query.get().user_id)
	Contestant.delete().execute()
	giveaway = Giveaway.get(active=True)
	giveaway.active=False
	giveaway.winner_id = winner.user_id
	giveaway.save()
	process_giveaway_transactions(giveaway.id, winner.user_id)
	return giveaway

# Returns True is contestant added, False if contestant already exists
def add_contestant(user_id):
	exists = Contestant.select().where(Contestant.user_id == user_id).count()
	if exists > 0:
		return False
	contestant = Contestant(user_id=user_id)
	contestant.save()
	return True

def is_active_giveaway():
	giveaway = Giveaway.select().where(Giveaway.active==True).count()
	if giveaway > 0:
		return True
	return False

# Gets giveaway stats
def get_giveaway_stats():
	try:
		giveaway = Giveaway.get(active=True)
		entries = Contestant.select().count()
		return {"amount":giveaway.amount + giveaway.tip_amount, "started_by":giveaway.started_by_name, "entries":entries, "end":giveaway.end_time}
	except Giveaway.DoesNotExist:
		return None

def inc_tx_attempts(uid):
	tx = Transaction.get(uid = uid)
	if tx is not None:
		tx.attempts += 1
		tx.save()
	return

def get_top_tips():
	dt = datetime.datetime.now()
	past_dt = dt - datetime.timedelta(days=1) # Date 24H ago
	month_str = dt.strftime("%B")
	month_num = "%02d" % dt.month # Sqlite uses 2 digit month (with leading 0)
	amount = fn.MAX(User.top_tip.cast('integer')).alias('amount')
	top_24h = User.select(amount, User.user_name).where(User.top_tip_ts > past_dt).order_by(User.top_tip_ts).limit(1)
	top_month = User.select(amount, User.user_name).where(fn.strftime("%m", User.top_tip_ts) == month_num).order_by(User.top_tip_ts).limit(1)
	top_at = User.select(amount, User.user_name).order_by(User.top_tip_ts).limit(1)
	# Formatted output
	user24h = None
	monthuser = None
	atuser = None

	for top in top_24h:
		user24h = top.user_name
		amount24h = float(top.amount) / 1000000
	for top in top_month:
		monthuser = top.user_name
		monthamount = float(top.amount) / 1000000
	for top in top_at:
		atuser = top.user_name
		atamount = float(top.amount) / 1000000

	if user24h is None and monthuser is None and atuser is None:
		return "```No Tips Found```"

	result = ""
	if user24h is not None:
		result += "Biggest tip in the last 24 hours:```%.6f NANO by %s```" % (amount24h, user24h)
	if monthuser is not None:
		result += "Biggest tip in %s:```%.6f NANO by %s```" % (month_str, monthamount, monthuser)
	if atuser is not None:
		result += "Biggest tip of all time:```%.6f NANO by %s```" % (atamount, atuser)

	return result

# You may think, this imposes serious double spend risks:
#  ie. if a transaction actually has been processed, but has never been marked processed in the database
#  This shouldn't happen even in that scenario, due to the id (uid here) field in nano node v10
def mark_transaction_processed(uuid, tranid, amt, source_id, target_id=None):
	tx = Transaction.get(uid=uuid)
	if tx is not None and not tx.processed:
		tx.processed=True
		tx.tran_id=tranid
		tx.save()
		update_pending(source_id, send=amt)
		if target_id is not None:
			update_pending(target_id, receive=amt)
	return

# Return false if last message was < LAST_MSG_TIME
# If > LAST_MSG_TIME, return True and update the user
# Also return true, if user does not have a tip bot acct yet
def last_msg_check(user_id):
	user = get_user_by_id(user_id)
	if user is None:
		return True
	# Get difference in seconds between now and last msg
	since_last_msg_s = (datetime.datetime.now() - user.last_msg).total_seconds()
	if since_last_msg_s < LAST_MSG_TIME:
		return False
	else:
		update_last_msg(user)
	return True

def update_last_msg(user):
	if user is not None:
		user.last_msg=datetime.datetime.now()
		user.save()
	return

# Update tip amount for stats (this value is saved as NANO not xrb)
def update_tipped_amt(user_id, tipped_amt):
	user = get_user_by_id(user_id)
	if user is not None:
		user.tipped_amount += tipped_amt / 1000000
		user.tip_count += 1
		user.save()
	return

# User table
class User(Model):
	user_id = CharField()
	user_name = CharField()
	wallet_address = CharField()
	tipped_amount = FloatField()
	wallet_balance = FloatField()
	pending_receive = IntegerField()
	pending_send = IntegerField()
	tip_count = BigIntegerField()
	created = DateTimeField()
	last_msg = DateTimeField()
	top_tip = CharField()
	top_tip_ts = DateTimeField()

	class Meta:
		database = db

# Transaction table, keep trac of sends to process
class Transaction(Model):
	uid = CharField()
	source_address = CharField()
	to_address = CharField(null = True)
	amount = CharField()
	processed = BooleanField()
	created = DateTimeField()
	tran_id = CharField()
	attempts = IntegerField()
	giveawayid = IntegerField(null = True)

	class Meta:
		database = db

# Giveaway table, keep track of current giveaway
class Giveaway(Model):
	started_by = CharField() # User ID
	started_by_name = CharField() # User Name
	active = BooleanField()
	amount = FloatField()
	tip_amount = FloatField()
	end_time = DateTimeField()
	channel_id = CharField() # The channel to post the results
	winner_id = CharField(null = True)

	class Meta:
		database = db

# Giveaway Entrants
class Contestant(Model):
	user_id = CharField()

	class Meta:
		database = db

def create_db():
	db.connect()
	db.create_tables([User, Transaction, Giveaway, Contestant], safe=True)
	logger.debug("DB Connected")

create_db()
