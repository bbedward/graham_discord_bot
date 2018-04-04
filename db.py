import datetime
import util
from peewee import *
from playhouse.sqliteq import SqliteQueueDatabase

# (Seconds) how long a user must wait in between messaging the bot
LAST_MSG_TIME = 1

# How many messages consider a user rain eligible
LAST_MSG_RAIN_COUNT = 5
# (Seconds) How spaced out the messages must be
LAST_MSG_RAIN_DELTA = 60
# How many words messages must contain
LAST_MSG_RAIN_WORDS = 3

db = SqliteQueueDatabase('nanotipbot.db')

logger = util.get_logger("db")

### User Stuff
def get_user_by_id(user_id):
	try:
		user = User.get(user_id=user_id)
		update_pending(user)
		return user
	except User.DoesNotExist:
		# logger.debug('user %s does not exist !', user_id)
		return None

def get_user_by_wallet_address(address):
	try:
		user = User.get(wallet_address=address)
		update_pending(user)
		return user
	except User.DoesNotExist:
		# logger.debug('wallet %s does not exist !', address)
		return None

def get_active_users(since_minutes):
	since_ts = datetime.datetime.now() - datetime.timedelta(minutes=since_minutes)
	users = User.select().where(User.last_msg > since_ts)
	return_ids = []
	for user in users:
		if user.last_msg_count >= LAST_MSG_RAIN_COUNT:
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
	user = get_user_by_id(user_id)
	if user is None:
		return None
	rank = User.select().where(User.tipped_amount > user.tipped_amount).count() + 1
	if user.tip_count == 0:
		average = 0
	else:
		average = user.tipped_amount / user.tip_count
	return {'rank':rank, 'total':user.tipped_amount, 'average':average,'top':float(user.top_tip) / 1000000}

# Update tip stats
def update_tip_stats(user, tip):
	if user is not None:
		user.tipped_amount += tip / 1000000
		user.tip_count += 1
		if tip > int(float(user.top_tip)):
			user.top_tip = tip
			user.top_tip_ts=datetime.datetime.now()
		user.save()
	return

def update_pending(user):
	if user is not None:
		pendings = PendingBalanceUpdate.select().where(PendingBalanceUpdate.user_id == user.user_id)
		if pendings.count() > 0:
			for p in pendings:
				user.pending_send += p.pending_send
				user.pending_receive += p.pending_receive
				p.delete_instance()
			user.save()

def queue_pending(user_id, send=0, receive=0):
	pbu = PendingBalanceUpdate(user_id=user_id,
			     pending_send=send,
			     pending_receive = receive
			    )
	pbu.save()
	return pbu

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
		    last_msg_rain=datetime.datetime.now(),
		    last_msg_count=0,
		    top_tip='0',
		    top_tip_ts=datetime.datetime.now(),
		    ticket_count=0
		    )
	user.save()
	return user

### Transaction Stuff
def create_transaction(src_usr, uuid, to_addr, amt, target_id=None, giveaway_id=0):
	tx = Transaction(uid=uuid,
			 source_address=src_usr.wallet_address,
			 to_address=to_addr,
			 amount=amt,
			 processed=False,
			 created=datetime.datetime.now(),
			 tran_id='',
			 attempts=0,
			 giveawayid=giveaway_id
			)
	tx.save()
	queue_pending(src_usr.user_id, send=amt)
	if target_id is not None:
		queue_pending(target_id, receive=amt)
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
	queue_pending(winner_user_id, receive=pending_receive)

# Start Giveaway
def start_giveaway(user_id, user_name, amount, end_time, channel, entry_fee = 0):
	giveaway = Giveaway(started_by=user_id,
			    started_by_name=user_name,
			    active=True,
			    amount = amount,
			    tip_amount = 0,
			    end_time=end_time,
			    channel_id = channel,
			    winner_id = None,
			    entry_fee = entry_fee
			   )
	giveaway.save()
	# Delete contestants not meeting fee criteria
	if entry_fee > 0:
		entries = Contestant.select()
		for c in entries:
			donated = get_tipgiveaway_contributions(c.user_id)
			if entry_fee > donated:
				c.delete_instance()
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
def get_tipgiveaway_contributions(user_id, giveawayid=-1):
	tip_sum = 0
	user = get_user_by_id(user_id)
	txs = Transaction.select().where((Transaction.giveawayid == giveawayid) & (Transaction.source_address == user.wallet_address))
	for tx in txs:
		tip_sum += int(tx.amount)
	return tip_sum

def is_banned(user_id):
	banned = BannedUser.select().where(BannedUser.user_id == user_id).count()
	return banned > 0

def ban_user(user_id):
	already_banned = is_banned(user_id)
	if already_banned > 0:
		return False
	ban = BannedUser(user_id=user_id)
	ban.save()
	return True

def unban_user(user_id):
	deleted = BannedUser.delete().where(BannedUser.user_id == user_id).execute()
	return deleted > 0

# Returns winning user
def finish_giveaway():
	picker_query = Contestant.select().where(Contestant.banned == False).order_by(fn.Random())
	winner = get_user_by_id(picker_query.get().user_id)
	Contestant.delete().execute()
	giveaway = Giveaway.get(active=True)
	giveaway.active=False
	giveaway.winner_id = winner.user_id
	giveaway.save()
	process_giveaway_transactions(giveaway.id, winner.user_id)
	# Undo shadow bans
	q = User.update({User.ticket_count:0})
	q.execute()
	return giveaway

# Returns True is contestant added, False if contestant already exists
def add_contestant(user_id, banned=False, override_ban=False):
	try:
		c = Contestant.get(Contestant.user_id == user_id)
		if c.banned and override_ban:
			c.banned=False
			c.save()
		return False
	except Contestant.DoesNotExist:
		contestant = Contestant(user_id=user_id,banned=banned)
		contestant.save()
		return True

def contestant_exists(user_id):
	c = Contestant.select().where(Contestant.user_id == user_id).count()
	return c > 0

def is_active_giveaway():
	giveaway = Giveaway.select().where(Giveaway.active==True).count()
	if giveaway > 0:
		return True
	return False

# Return true if shadow banned, or banned in general
def ticket_spam_check(user_id, increment=True):
	user = get_user_by_id(user_id)
	if user is None:
		return False
	if is_banned(user_id):
		return True
	if increment:
		user.ticket_count += 1
		user.save()
	return user.ticket_count >= 3

# Gets giveaway stats
def get_giveaway_stats():
	try:
		giveaway = Giveaway.get(active=True)
		entries = Contestant.select().count()
		return {"amount":giveaway.amount + giveaway.tip_amount, "started_by":giveaway.started_by_name, "entries":entries, "end":giveaway.end_time,"fee":giveaway.entry_fee}
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

# This marks transactions in our local log as processed (sent to node0
def mark_transaction_processed(uuid, tranid, amt, source_id, target_id=None):
	tx = Transaction.get(uid=uuid)
	if tx is not None and not tx.processed:
		tx.processed=True
		tx.tran_id=tranid
		tx.save()
		queue_pending(source_id, send=amt)
		if target_id is not None:
			queue_pending(target_id, receive=amt)
	return

# Return false if last message was < LAST_MSG_TIME
# If > LAST_MSG_TIME, return True and update the user
# Also return true, if user does not have a tip bot acct yet
def last_msg_check(user_id, content, is_private):
	user = get_user_by_id(user_id)
	if user is None:
		return True
	# Get difference in seconds between now and last msg
	since_last_msg_s = (datetime.datetime.now() - user.last_msg).total_seconds()
	if since_last_msg_s < LAST_MSG_TIME:
		return False
	else:
		update_last_msg(user, since_last_msg_s, content, is_private)
	return True

def update_last_msg(user, delta, content, is_private):
	words = len(content.split(' '))
	if delta >= 1800:
		user.last_msg_count = 0
	if words >= LAST_MSG_RAIN_WORDS and not is_private and (datetime.datetime.now() - user.last_msg_rain).total_seconds() > LAST_MSG_RAIN_DELTA:
		user.last_msg_count += 1
		user.last_msg_rain = datetime.datetime.now()
	user.last_msg=datetime.datetime.now()
	user.save()
	return

def mark_user_active(user):
	if user is None:
		return
	if LAST_MSG_RAIN_COUNT > user.last_msg_count:
		user.last_msg_count = 5
		user.save()

# User table
class User(Model):
	user_id = CharField(unique=True)
	user_name = CharField()
	wallet_address = CharField(unique=True)
	tipped_amount = FloatField()
	wallet_balance = FloatField()
	pending_receive = IntegerField()
	pending_send = IntegerField()
	tip_count = BigIntegerField()
	created = DateTimeField()
	last_msg = DateTimeField()
	last_msg_rain = DateTimeField()
	last_msg_count = IntegerField()
	top_tip = CharField()
	top_tip_ts = DateTimeField()
	ticket_count = IntegerField()

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

# PendingBalanceUpdate table, written by SendProcessor and used to update User whenever one is retrieved
class PendingBalanceUpdate(Model):
	user_id = ForeignKeyField(User, backref='pendings')
	pending_send = IntegerField(null = False, default = 0)
	pending_receive = IntegerField(null = False, default = 0)


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
	entry_fee = IntegerField()

	class Meta:
		database = db

# Giveaway Entrants
class Contestant(Model):
	user_id = CharField()
	banned = BooleanField()

	class Meta:
		database = db

# Banned List
class BannedUser(Model):
	user_id = CharField()

	class Meta:
		database = db

def create_db():
	db.connect()
	db.create_tables([User, Transaction, PendingBalanceUpdate, Giveaway, Contestant, BannedUser], safe=True)
	logger.debug("DB Connected")

create_db()
