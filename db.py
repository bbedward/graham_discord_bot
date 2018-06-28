import json
import re
import datetime
import util
import settings
import random
import secrets

from peewee import *
from playhouse.pool  import PooledPostgresqlExtDatabase
from playhouse.shortcuts import model_to_dict

# TODO - Redesign the schema
# - TipBot grew into more than a tip bot quickly as features piled on
#   combined with a non-backwards compatible discord.py update and
#   the fact I never worked with python or peewee before this project.
#   So eventual schema redesign plans:
# 1) Discord IDs are now integers. Every discord ID stored should become IntegerField
# 2) Giveaway transactions should be further distinguished from normal TXs
#    after a giveaway is over, it's impossible to tell what transactions were part of the
#    giveaway. That's a mild design flaw
# 3) Where applicable replace peewee default primary key with discord ID as primary key
#    many of our queries are written using discord IDs already.
#    e.g. user_id should be PrimaryKeyField on users table
# 4) De-couple stats, accounts, etc. from users table.
#    (Make a one-to-many relationship between a users and stats/accounts table)
#    Why one-to-many instead of 1-1 for accounts? see point 8
# 5) Foreign key relationships everywhere
# 6) We only retrieve a DB connection 1 time, which isn't much of a problem for SQLite,
#    but perhaps a better practice would be to create and destroy connections as needed
#    which brings the next point:
# 7) SQLite is fine for our purposes, but some operations would be much better if we
#    could do them atomically. (e.g. when multiple DB operations occur, if  one fails
#    then everything rolls back). Not a problem with SQLite or peewee, per say, but
#    due to multithreading issues we use SQliteQueueDatabase which queues writes
#    synchronously and that breaks atomic transactions.
#    so....maybe eye a switch to MySQL or PostgreSQL
# 8) Attach discord server ID to user accounts, stats, etc.
#    this will allow some important things for the future of NANO/BANANO bots
#    Mainly, allowing the bot to be used on multiple servers
#
# Of course, we need a way to migrate the old database into this re-design

# (Seconds) how long a user must wait in between messaging the bot
LAST_MSG_TIME = 1

# How many messages consider a user rain eligible
LAST_MSG_RAIN_COUNT = 5
# (Seconds) How spaced out the messages must be
LAST_MSG_RAIN_DELTA = 60
# How many words messages must contain
LAST_MSG_RAIN_WORDS = 3

# (Seconds) How long user must wait between tiprandom
TIP_RANDOM_WAIT = 10
# (Seconds) How long user mus wait between tipfavorites
TIP_FAVORITES_WAIT = 150

db = PooledPostgresqlExtDatabase(settings.database, user=settings.database_user, password=settings.database_password, host='localhost', port=5432, max_connections=16)

logger = util.get_logger("db")

### User Stuff
@db.connection_context()
def get_accounts():
	u = User.select(User.wallet_address)
	accts = []
	for a in u:
		accts.append(a.wallet_address)
	return accts

@db.connection_context()
def get_user_by_id(user_id, user_name=None):
	try:
		user = User.get(user_id=str(user_id))
		if user_name is not None and user_name != user.user_name:
			User.update(user_name=user_name).where(User.id == user.id).execute()
			user.user_name = user_name
		return user
	except User.DoesNotExist:
		# logger.debug('user %s does not exist !', user_id)
		return None

@db.connection_context()
def get_user_by_wallet_address(address):
	try:
		user = User.get(wallet_address=address)
		return user
	except User.DoesNotExist:
		# logger.debug('wallet %s does not exist !', address)
		return None

@db.connection_context()
def user_exists(user_id):
	return User.select().where(User.user_id == user_id).count() > 0

@db.connection_context()
def get_active_users(since_minutes):
	since_ts = datetime.datetime.utcnow() - datetime.timedelta(minutes=since_minutes)
	users = User.select().where(User.last_msg > since_ts).order_by(User.user_id)
	return_ids = []
	for user in users:
		if user.last_msg_count >= LAST_MSG_RAIN_COUNT:
			if is_banned(user.user_id):
				continue
			return_ids.append(user.user_id)
	return return_ids

@db.connection_context()
def get_address(user_id):
	logger.info('getting wallet address for user %d ...', user_id)
	user = get_user_by_id(user_id)
	if user is None:
		return None
	else:
		return user.wallet_address

@db.connection_context()
def get_top_users(count):
	users = User.select().where((User.tipped_amount > 0) & (User.stats_ban == False)).order_by(User.tipped_amount.desc()).limit(count)
	return_data = []
	for idx, user in enumerate(users):
		return_data.append({'index': idx + 1, 'name': user.user_name, 'amount': user.tipped_amount})
	return return_data

@db.connection_context()
def get_giveaway_winners(count):
	winners = Giveaway.select().where((Giveaway.active == False) & (Giveaway.winner_id.is_null(False))).order_by(Giveaway.end_time.desc()).limit(count)
	return_data = []
	for idx, winner in enumerate(winners):
		user = get_user_by_id(winner.winner_id)
		return_data.append({'index': idx + 1, 'name': user.user_name, 'amount': winner.amount + winner.tip_amount})
	return return_data

@db.connection_context()
def get_tip_stats(user_id):
	user_id = str(user_id)
	user = get_user_by_id(user_id)
	if user is None:
		return None
	rank = User.select().where((User.tipped_amount > user.tipped_amount) & (User.stats_ban == False)).count() + 1
	if not user.stats_ban:
		tipped_amount = user.tipped_amount
		tip_count = user.tip_count
		top_tip = user.top_tip if settings.banano else float(user.top_tip) / 1000000
	else:
		tipped_amount = 0
		tip_count = 0
		top_tip = 0
		rank = -1
	if tip_count == 0:
		average = 0
	else:
		average = tipped_amount / tip_count
	return {'rank':rank, 'total':tipped_amount, 'average':average,'top':top_tip}

# Update tip stats
@db.connection_context()
def update_tip_stats(user, tip, rain=False, giveaway=False):
	tip_add = tip if settings.banano else tip / 1000000
	(User.update(
		tipped_amount=(User.tipped_amount + (tip_add)),
		tip_count = User.tip_count + 1
		).where(User.id == user.id)
		).execute()
	# Update all time tip if necessary
	if tip > int(float(user.top_tip)):
		(User.update(
			top_tip = tip,
			top_tip_ts = datetime.datetime.utcnow()
			).where(User.id == user.id)
			).execute()
	# Update monthly tip if necessary
	if user.top_tip_month_ts.month != datetime.datetime.utcnow().month or tip > int(float(user.top_tip_month)):
		(User.update(
			top_tip_month = tip,
			top_tip_month_ts = datetime.datetime.utcnow()
			).where(User.id == user.id)
			).execute()
	# Update 24H tip if necessary
	delta = datetime.datetime.utcnow() - user.top_tip_day_ts
	if delta.total_seconds() > 86400 or tip > int(float(user.top_tip_day)):
		(User.update(
			top_tip_day = tip,
			top_tip_day_ts = datetime.datetime.utcnow()
			).where(User.id == user.id)
			).execute()
	# Update rain or giveaway stats
	if rain:
		(User.update(
			rain_amount = User.rain_amount + (tip_add)
			)
			.where(User.id == user.id)
		).execute()
	elif giveaway:
		(User.update(
			giveaway_amount = User.giveaway_amount + (tip_add)
			)
			.where(User.id == user.id)
		).execute()

@db.connection_context()
def update_tip_total(user_id, new_total):
	user_id = str(user_id)
	User.update(tipped_amount = new_total).where(User.user_id == user_id).execute()
	return

@db.connection_context()
def update_tip_count(user_id, new_count):
	user_id = str(user_id)
	User.update(tip_count = new_count).where(User.user_id == user_id).execute()
	return

@db.connection_context()
def update_pending(user_id, send=0, receive=0):
	user_id=str(user_id)
	return (User.update(
			pending_send = (User.pending_send + send),
			pending_receive = (User.pending_receive + receive)
		    ).where(User.user_id == user_id)
		).execute()

@db.connection_context()
def create_user(user_id, user_name, wallet_address):
	user_id=str(user_id)
	user = User(user_id=user_id,
		    user_name=user_name,
		    wallet_address=wallet_address,
		    )
	user.save()
	return user

### Transaction Stuff
@db.connection_context()
def create_transaction(src_usr, uuid, to_addr, amt, target_id=None, giveaway_id=0):
	# Increment amount of giveaway TX if user has already donated to giveaway
	if giveaway_id != 0:
		try:
			giveawayTx = (Transaction.select()
						 .where(
							(Transaction.source_address == src_usr.wallet_address) &
							(Transaction.giveawayid == giveaway_id)
							)
				     ).get()
			update = (Transaction.update(amount = Transaction.amount.cast('integer') + amt)
				    	.where(Transaction.id == giveawayTx.id)
				 ).execute()
			if update > 0:
				update_pending(src_usr.user_id, send=amt)
			return
		except Transaction.DoesNotExist:
			pass

	tx = Transaction(uid=uuid,
			 source_address=src_usr.wallet_address,
			 to_address=to_addr,
			 amount=amt,
			 giveawayid=giveaway_id
			)
	tx.save()
	update_pending(src_usr.user_id, send=amt)
	if target_id is not None:
		update_pending(target_id, receive=amt)
	if tx.giveawayid == 0:
		process_transaction(tx)
	return tx

def process_transaction(tx):
	from tasks import send_transaction
	send_transaction.delay(model_to_dict(tx))

@db.connection_context()
def update_last_withdraw(user_id):
	user_id = str(user_id)
	User.update(last_withdraw=datetime.datetime.utcnow()).where(User.user_id == user_id).execute()

@db.connection_context()
def get_last_withdraw_delta(user_id):
	user_id = str(user_id)
	try:
		user = User.select(User.last_withdraw).where(User.user_id == user_id).get()
		delta = (datetime.datetime.utcnow() - user.last_withdraw).total_seconds()
		return delta
	except User.DoesNotExist:
		return None

def tx_to_dict(tx):
	return {'uid':tx.uid,'source_address':tx.source_address,'to_address':tx.to_address,'amount':tx.amount,'attempts':tx.attempts}

@db.connection_context()
def process_giveaway_transactions(giveaway_id, winner_user_id):
	txs = Transaction.select().where(Transaction.giveawayid == giveaway_id)
	winner = get_user_by_id(winner_user_id)
	pending_receive = 0
	for tx in txs:
		tx.to_address = winner.wallet_address
		pending_receive += int(tx.amount)
		process_transaction(tx)
	update_pending(winner_user_id, receive=pending_receive)
	(Transaction.update(
			to_address = winner.wallet_address
		    ).where(
			(Transaction.giveawayid == giveaway_id)
	)).execute()

# Start Giveaway
@db.connection_context()
def start_giveaway(user_id, user_name, amount, end_time, channel, entry_fee = 0):
	user_id=str(user_id)
	channel=str(channel)
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
	deleted = []
	if entry_fee > 0:
		entries = Contestant.select()
		for c in entries:
			donated = get_tipgiveaway_contributions(c.user_id)
			if entry_fee > donated:
				c.delete_instance()
				deleted.append(c.user_id)
	tip_amt = update_giveaway_transactions(giveaway.id)
	giveaway.tip_amount = tip_amt
	giveaway.save()
	return (giveaway, deleted)

@db.connection_context()
def get_giveaway():
	try:
		giveaway = Giveaway.get(active=True)
		return giveaway
	except:
		return None

@db.connection_context()
def update_giveaway_transactions(giveawayid):
	tip_sum = 0
	txs = Transaction.select().where(Transaction.giveawayid == -1)
	for tx in txs:
		tip_sum += int(tx.amount)
	(Transaction.update(
			giveawayid = giveawayid
		    ).where(
			(Transaction.giveawayid == -1)
	)).execute()

	return float(tip_sum) if settings.banano else float(tip_sum)/ 1000000

@db.connection_context()
def add_tip_to_giveaway(amount):
	giveawayupdt = (Giveaway
				.update(
					tip_amount = (Giveaway.tip_amount + amount)
				).where(Giveaway.active == True)
			).execute()

@db.connection_context()
def get_tipgiveaway_sum():
	tip_sum = 0
	txs = Transaction.select().where(Transaction.giveawayid == -1)
	for tx in txs:
		tip_sum += int(tx.amount)
	return tip_sum

# Get tipgiveaway contributions
@db.connection_context()
def get_tipgiveaway_contributions(user_id, giveawayid=-1):
	tip_sum = 0
	user = get_user_by_id(user_id)
	txs = Transaction.select().where((Transaction.giveawayid == giveawayid) & (Transaction.source_address == user.wallet_address))
	for tx in txs:
		tip_sum += int(tx.amount)
	return tip_sum

@db.connection_context()
def is_banned(user_id):
	user_id=str(user_id)
	banned = BannedUser.select().where(BannedUser.user_id == user_id).count()
	return banned > 0

@db.connection_context()
def ban_user(user_id):
	user_id = str(user_id)
	already_banned = is_banned(user_id)
	if already_banned > 0:
		return False
	ban = BannedUser(user_id=user_id)
	ban.save()
	return True

@db.connection_context()
def statsban_user(user_id):
	user_id = str(user_id)
	banned = User.update(stats_ban = True).where(User.user_id == user_id).execute()
	return banned > 0

@db.connection_context()
def unban_user(user_id):
	user_id = str(user_id)
	deleted = BannedUser.delete().where(BannedUser.user_id == user_id).execute()
	return deleted > 0

@db.connection_context()
def statsunban_user(user_id):
	user_id = str(user_id)
	unbanned = User.update(stats_ban = False).where(User.user_id == user_id).execute()
	return unbanned > 0

@db.connection_context()
def get_banned():
	banned = BannedUser.select(BannedUser.user_id)
	users = User.select(User.user_name).where(User.user_id.in_(banned))
	if users.count() == 0:
		return "```Nobody Banned```"
	ret = "```"
	for idx,user in enumerate(users):
		ret += "{0}: {1}\n".format(idx+1,user.user_name)
	ret += "```"
	return ret

@db.connection_context()
def get_statsbanned():
	statsbanned = User.select().where(User.stats_ban == True)
	if statsbanned.count() == 0:
		return "```No stats bans```"
	ret = "```"
	for idx,user in enumerate(statsbanned):
		ret += "{0}: {1}\n".format(idx+1,user.user_name)
	ret += "```"
	return ret

@db.connection_context()
def is_frozen(user_id):
	return FrozenUser.select().where(FrozenUser.user_id == user_id).count() > 0

@db.connection_context()
def freeze(user):
	if not is_frozen(user.id):
		fu = FrozenUser(user_id=user.id, user_name=user.name)
		saved = fu.save()
		return saved > 0
	return False

@db.connection_context()
def unfreeze(user_id):
	if not is_frozen(user_id):
		return False
	return FrozenUser.delete().where(FrozenUser.user_id==user_id).execute() > 0

@db.connection_context()
def frozen():
	frozen = FrozenUser.select()
	if frozen.count() == 0:
		return "```Nobody Frozen```"
	ret = "```"
	for idx, fu in enumerate(frozen):
		ret += "{0}: {1}\n".format(idx+1, fu.user_name)
	ret += "```"
	return ret

# Returns winning user
@db.connection_context()
def finish_giveaway():
	contestants = Contestant.select(Contestant.user_id).order_by(Contestant.user_id)
	contestant_ids = []
	for c in contestants:
		contestant_ids.append(c.user_id)
	sysrand = random.SystemRandom()
	sysrand.shuffle(contestant_ids)
	offset = secrets.randbelow(len(contestant_ids))
	winner = get_user_by_id(contestant_ids[offset])
	Contestant.delete().execute()
	giveaway = Giveaway.get(active=True)
	giveaway.active=False
	giveaway.winner_id = winner.user_id
	giveaway.save()
	process_giveaway_transactions(giveaway.id, winner.user_id)
	return giveaway

# Returns True is contestant added, False if contestant already exists
@db.connection_context()
def add_contestant(user_id):
	user_id=str(user_id)
	exists = Contestant.select().where(Contestant.user_id == user_id).count() > 0
	if exists:
		return False
	contestant = Contestant(user_id=user_id,banned=False)
	contestant.save()
	return True

@db.connection_context()
def get_ticket_status(user_id):
	user_id = str(user_id)
	try:
		giveaway = Giveaway.select().where(Giveaway.active==True).get()
		if contestant_exists(user_id):
			return "You are already entered into the giveaway!"
		fee = giveaway.entry_fee
		contributions = get_tipgiveaway_contributions(user_id, giveawayid=giveaway.id)
		cost = fee - contributions
		return_str = ("You do not have a ticket to the current giveaway!\n" +
				"Giveaway fee: {0}\n" +
				"Your donations: {1}\n" +
				"Your ticket cost: {2}\n\n" +
				"You may enter using `{3}ticket {2}`").format(fee, contributions, cost, settings.command_prefix)
		return return_str
	except Giveaway.DoesNotExist:
		contributions = get_tipgiveaway_contributions(user_id)
		return ("There is no active giveaway.\n" +
			"So far you've contributed {0} {1} towards the next one.\n" +
			"I'll automatically enter you into the next giveaway if the fee is <= {0} {1}").format(contributions, "BANANO" if settings.banano else "naneroo")

@db.connection_context()
def contestant_exists(user_id):
	user_id = str(user_id)
	c = Contestant.select().where(Contestant.user_id == user_id).count()
	return c > 0

@db.connection_context()
def is_active_giveaway():
	giveaway = Giveaway.select().where(Giveaway.active==True).count()
	if giveaway > 0:
		return True
	return False

# Gets giveaway stats
@db.connection_context()
def get_giveaway_stats():
	try:
		giveaway = Giveaway.get(active=True)
		entries = Contestant.select().count()
		return {"amount":giveaway.amount + giveaway.tip_amount, "started_by":giveaway.started_by_name, "entries":entries, "end":giveaway.end_time,"fee":giveaway.entry_fee}
	except Giveaway.DoesNotExist:
		return None

@db.connection_context()
def inc_tx_attempts(uid):
	tx = Transaction.get(uid = uid)
	if tx is not None:
		tx.attempts += 1
		tx.save()
	return

@db.connection_context()
def update_top_tips(user_id, month=0,day=0,alltime=0):
	return (User.update(top_tip = User.top_tip + alltime,
			    top_tip_month = User.top_tip_month + month,
		 	    top_tip_day = User.top_tip_day + day
		  	   ).where(User.user_id == user_id)).execute()

@db.connection_context()
def get_top_tips():
	dt = datetime.datetime.utcnow()
	past_dt = dt - datetime.timedelta(days=1) # Date 24H ago
	month_str = dt.strftime("%B")
	top_24h = (User.select(User.top_tip_day.alias('amount'), User.user_name)
			.where((User.top_tip_day_ts > past_dt) &
				(User.stats_ban == False))
			.group_by(User.user_name, User.top_tip_day)
			.having(User.top_tip_day == fn.MAX(User.top_tip_day))
			.order_by(User.top_tip_day.desc())
			.limit(1))
	top_month = (User.select(User.top_tip_month.alias('amount'), User.user_name)
			.where((fn.date_part('month', User.top_tip_month_ts) == str(dt.month)) &
				(User.stats_ban == False))
			.group_by(User.user_name, User.top_tip_month)
			.having(User.top_tip_month == fn.MAX(User.top_tip_month))
			.order_by(User.top_tip_month.desc())
			.limit(1))
	top_at = (User.select(User.top_tip.alias('amount'), User.user_name)
			.where(User.stats_ban == False)
			.group_by(User.user_name, User.top_tip)
			.having(User.top_tip == fn.MAX(User.top_tip))
			.order_by(User.top_tip.desc())
			.limit(1))
	# Formatted output
	user24h = None
	monthuser = None
	atuser = None

	for top in top_24h:
		user24h = top.user_name
		amount24h = float(top.amount) if settings.banano else float(top.amount) / 1000000
	for top in top_month:
		monthuser = top.user_name
		monthamount = float(top.amount) if settings.banano else float(top.amount) / 1000000
	for top in top_at:
		atuser = top.user_name
		atamount = float(top.amount) if settings.banano else float(top.amount) / 1000000

	if user24h is None and monthuser is None and atuser is None:
		return "```No Tips Found```"

	result = ""
	if user24h is not None:
		if settings.banano:
			result += "Biggest tip in the last 24 hours:```{0:.2f} BANANO by {1}```".format(amount24h, user24h)
		else:
			result += "Biggest tip in the last 24 hours:```{0:.6f} NANO by {1}```".format(amount24h, user24h)
	if monthuser is not None:
		if settings.banano:
			result += "Biggest tip in {0}:```{1:.2f} BANANO by {2}```".format(month_str, monthamount, monthuser)
		else:
			result += "Biggest tip in {0}:```{1:.6f} NANO by {2}```".format(month_str, monthamount, monthuser)
	if atuser is not None:
		if settings.banano:
			result += "Biggest tip of all time:```{0:.2f} BANANO by {1}```".format(atamount, atuser)
		else:
			result += "Biggest tip of all time:```{0:.6f} NANO by {1}```".format(atamount, atuser)

	return result

# Marks TX as processed and adds the block hash
@db.connection_context()
def mark_transaction_processed(uuid, amt, source_id, tranid, target_id=None):
	tu = (Transaction.update(
			processed = True,
			tran_id = tranid
		    ).where(
			(Transaction.uid == uuid) &
			(Transaction.processed == False)
	)).execute()
	if tu > 0:
		update_pending(source_id,send=amt)
		if target_id is not None:
			update_pending(target_id, receive=amt)

@db.connection_context()
def update_block_hash(id, hash):
	return Transaction.update(tran_id=hash).where(Transaction.uid == id).execute() > 0

# Return false if last message was < LAST_MSG_TIME
# If > LAST_MSG_TIME, return True and update the user
# Also return true, if user does not have a tip bot acct yet
@db.connection_context()
def last_msg_check(user_id, content, is_private):
	user = get_user_by_id(user_id)
	if user is None:
		return True
	# Get difference in seconds between now and last msg
	since_last_msg_s = (datetime.datetime.utcnow() - user.last_msg).total_seconds()
	if since_last_msg_s < LAST_MSG_TIME:
		return False
	else:
		update_last_msg(user, since_last_msg_s, content, is_private)
	return True

@db.connection_context()
def update_last_msg(user, delta, content, is_private):
	content_adjusted = unicode_strip(content)
	words = content_adjusted.split(' ')
	adjusted_count = 0
	prev_len = 0
	for word in words:
		word = word.strip()
		cur_len = len(word)
		if cur_len > 0:
			if word.startswith(":") and word.endswith(":"):
				continue
			if prev_len == 0:
				prev_len = cur_len
				adjusted_count += 1
			else:
				res = prev_len % cur_len
				prev_len = cur_len
				if res != 0:
					adjusted_count += 1
		if adjusted_count >= LAST_MSG_RAIN_WORDS:
			break
	if delta >= 1800:
		user.last_msg_count = 0
	if adjusted_count >= LAST_MSG_RAIN_WORDS and not is_private and (datetime.datetime.utcnow() - user.last_msg_rain).total_seconds() > LAST_MSG_RAIN_DELTA:
		user.last_msg_count += 1
		user.last_msg_rain = datetime.datetime.utcnow()
	user.last_msg=datetime.datetime.utcnow()
	(User.update(
		last_msg_count = user.last_msg_count,
		last_msg_rain = user.last_msg_rain,
		last_msg = user.last_msg
	    ).where(User.user_id == user.user_id)
	).execute()
	return

@db.connection_context()
def unicode_strip(content):
	pattern = re.compile("["
			u"\U0001F600-\U0001F64F"
			u"\U0001F300-\U0001F5FF"
			u"\U0001F1E0-\U0001F1FF"
			u"\U00002702-\U000027B0"
			u"\U000024C2-\U0001F251"
			"]+", flags=re.UNICODE)
	return pattern.sub(r'',content)

@db.connection_context()
def mark_user_active(user):
	if user is None:
		return
	if LAST_MSG_RAIN_COUNT > user.last_msg_count:
		(User.update(
			last_msg_count = LAST_MSG_RAIN_COUNT
		    ).where(User.user_id == user.user_id)
		).execute()

## Favorites

# Return true if favorite added
@db.connection_context()
def add_favorite(user_id, favorite_id):
	user_id=str(user_id)
	favorite_id=str(favorite_id)
	if not user_exists(favorite_id):
		return False
	count = UserFavorite.select().where(UserFavorite.user_id == user_id).count()
	# Identifier makes it easy for user to remove their favorite via DM
	if count == 0:
		identifier = 1
	else:
		identifier = count + 1
	exists = UserFavorite.select().where((UserFavorite.user_id == user_id) & (UserFavorite.favorite_id == favorite_id)).count()
	if exists == 0:
		fav = UserFavorite(user_id=user_id,favorite_id=favorite_id,identifier=identifier)
		fav.save()
		return True
	return False

# Returns true if favorite deleted
@db.connection_context()
def remove_favorite(user_id, favorite_id=None,identifier=None):

	if favorite_id is None and identifier is None:
		return False
	user_id=str(user_id)
	if favorite_id is not None:
		favorite_id = str(favorite_id)
		return UserFavorite.delete().where((UserFavorite.user_id == user_id) & (UserFavorite.favorite_id == favorite_id)).execute() > 0
	elif identifier is not None:
		return UserFavorite.delete().where((UserFavorite.user_id == user_id) & (UserFavorite.identifier == identifier)).execute() > 0

# Returns list of favorites for user ID
@db.connection_context()
def get_favorites_list(user_id):
	user_id = str(user_id)
	favorites = UserFavorite.select().where(UserFavorite.user_id==user_id).order_by(UserFavorite.identifier)
	idx = 1
	# Normalize identifiers
	for fav in favorites:
		fav.identifier = idx
		UserFavorite.update(identifier=idx).where((UserFavorite.user_id==user_id) & (UserFavorite.favorite_id == fav.favorite_id)).execute()
		idx += 1
	return_data = []
	for fav in favorites:
		return_data.append({'user_id':fav.favorite_id,'id': fav.identifier})
	return return_data

# Returns list of muted for user id
@db.connection_context()
def get_muted(user_id):
	user_id = str(user_id)
	muted = MutedList.select().where(MutedList.user_id==user_id)
	return_data = []
	for m in muted:
		return_data.append({'name':m.muted_name, 'id': m.muted_id})
	return return_data

# Return True if muted
@db.connection_context()
def muted(source_user, target_user):
	source_user = str(source_user)
	target_user = str(target_user)
	return MutedList.select().where((MutedList.user_id==source_user) & (MutedList.muted_id==target_user)).count() > 0

# Return false if already muted, True if muted
@db.connection_context()
def mute(source_user, target_user, target_name):
	if muted(source_user, target_user):
		return False
	source_user = str(source_user)
	target_user = str(target_user)
	mute = MutedList(user_id=source_user,muted_id=target_user,muted_name=target_name)
	mute.save()
	return True

# Return a number > 0 if user was unmuted
@db.connection_context()
def unmute(source_user, target_user):
	source_user = str(source_user)
	target_user = str(target_user)
	return MutedList.delete().where((MutedList.user_id==source_user) & (MutedList.muted_id==target_user)).execute()


# Returns seconds user must wait to tiprandom again
@db.connection_context()
def tiprandom_check(user):
	delta = (datetime.datetime.utcnow() - user.last_random).total_seconds()
	if TIP_RANDOM_WAIT > delta:
		return (TIP_RANDOM_WAIT - delta)
	else:
		User.update(last_random=datetime.datetime.utcnow()).where(User.user_id == user.user_id).execute()
		return 0

# Returns seconds user must wait to tipfavorites again
@db.connection_context()
def tipfavorites_check(user):
	delta = (datetime.datetime.utcnow() -user.last_favorites).total_seconds()
	if TIP_FAVORITES_WAIT > delta:
		return (TIP_FAVORITES_WAIT - delta)
	else:
		User.update(last_favorites=datetime.datetime.utcnow()).where(User.user_id == user.user_id).execute()
		return 0

# Base Model
class BaseModel(Model):
	class Meta:
		database = db
# User table
class User(BaseModel):
	user_id = CharField(unique=True)
	user_name = CharField()
	wallet_address = CharField(unique=True)
	tipped_amount = FloatField(default=0.0)
	pending_receive = IntegerField(default=0)
	pending_send = IntegerField(default=0)
	tip_count = IntegerField(default=0)
	created = DateTimeField(default=datetime.datetime.utcnow())
	last_msg = DateTimeField(default=datetime.datetime.utcnow())
	last_msg_rain = DateTimeField(default=datetime.datetime.utcnow())
	last_msg_count = IntegerField(default=0)
	top_tip = IntegerField(default=0)
	top_tip_ts = DateTimeField(default=datetime.datetime.utcnow())
	top_tip_month = IntegerField(default=0)
	top_tip_month_ts = DateTimeField(default=datetime.datetime.utcnow())
	top_tip_day = IntegerField(default=0)
	top_tip_day_ts = DateTimeField(default=datetime.datetime.utcnow())
	last_withdraw = DateTimeField(default=datetime.datetime.utcnow())
	stats_ban = BooleanField(default=False)
	rain_amount = FloatField(default=0.0,)
	giveaway_amount = FloatField(default=0.0)
	last_random = DateTimeField(default=datetime.datetime.utcnow())
	last_favorites = DateTimeField(default=datetime.datetime.utcnow())

	class Meta:
		db_table='users'

# Transaction table, keep trac of sends to process
class Transaction(BaseModel):
	uid = CharField(unique=True)
	source_address = CharField()
	to_address = CharField(null = True)
	amount = CharField()
	processed = BooleanField(default=False)
	created = DateTimeField(default=datetime.datetime.utcnow())
	tran_id = CharField(default=None, null=True)
	attempts = IntegerField(default=0)
	giveawayid = IntegerField(null = True)

	class Meta:
		db_table='transactions'

# Giveaway table, keep track of current giveaway
class Giveaway(BaseModel):
	started_by = CharField() # User ID
	started_by_name = CharField() # User Name
	active = BooleanField()
	amount = FloatField()
	tip_amount = FloatField()
	end_time = DateTimeField()
	channel_id = CharField() # The channel to post the results
	winner_id = CharField(null = True)
	entry_fee = IntegerField()

# Giveaway Entrants
class Contestant(BaseModel):
	user_id = CharField(unique=True)
	banned = BooleanField()

# Banned List
class BannedUser(BaseModel):
	user_id = CharField()

# Favorites List
class UserFavorite(BaseModel):
	user_id = CharField()
	favorite_id = CharField()
	created = DateTimeField(default=datetime.datetime.utcnow())
	identifier = IntegerField() # Identifier makes it easy for user to remove this favorite

# Muted management
class MutedList(BaseModel):
	user_id = CharField()
	muted_id = CharField()
	muted_name = CharField()
	created = DateTimeField(default=datetime.datetime.utcnow())

# Separate table for frozen so we can freeze even users not registered with bot
class FrozenUser(BaseModel):
	user_id = IntegerField(unique=True)
	user_name = CharField()
	created = DateTimeField(default=datetime.datetime.utcnow())


def create_db():
	with db.connection_context():
		db.create_tables([User, Transaction, Giveaway, Contestant, BannedUser, UserFavorite, MutedList, FrozenUser], safe=True)

create_db()
