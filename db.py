import re
import datetime
import util
import settings
from random import randint
from random import shuffle
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
		user = User.get(user_id=str(user_id))
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

def user_exists(user_id):
	return User.select().where(User.user_id == user_id).count() > 0

def get_active_users(since_minutes):
	since_ts = datetime.datetime.now() - datetime.timedelta(minutes=since_minutes)
	users = User.select().where(User.last_msg > since_ts)
	return_ids = []
	for user in users:
		if user.last_msg_count >= LAST_MSG_RAIN_COUNT:
			return_ids.append(user.user_id)
	return return_ids

def get_address(user_id):
	user_id = str(user_id)
	logger.info('getting wallet address for user %s ...', user_id)
	user = get_user_by_id(user_id)
	if user is None:
		return None
	else:
		return user.wallet_address

def get_top_users(count):
	users = User.select().where((User.tipped_amount > 0) & (User.stats_ban == False)).order_by(User.tipped_amount.desc()).limit(count)
	return_data = []
	for idx, user in enumerate(users):
		return_data.append({'index': idx + 1, 'name': user.user_name, 'amount': user.tipped_amount})
	return return_data

def get_giveaway_winners(count):
	winners = Giveaway.select().where((Giveaway.active == False) & (Giveaway.winner_id.is_null(False))).order_by(Giveaway.end_time.desc()).limit(count)
	return_data = []
	for idx, winner in enumerate(winners):
		user = get_user_by_id(winner.winner_id)
		return_data.append({'index': idx + 1, 'name': user.user_name, 'amount': winner.amount + winner.tip_amount})
	return return_data

def get_tip_stats(user_id):
	user_id = str(user_id)
	user = get_user_by_id(user_id)
	if user is None:
		return None
	rank = User.select().where(User.tipped_amount > user.tipped_amount).count() + 1
	if not user.stats_ban:
		tipped_amount = user.tipped_amount
		tip_count = user.tip_count
		top_tip = user.top_tip
	else:
		tipped_amount = 0
		tip_count = 0
		top_tip = 0
	if tip_count == 0:
		average = 0
	else:
		average = tipped_amount / tip_count
	return {'rank':rank, 'total':tipped_amount, 'average':average,'top':float(top_tip) / 1000000}

# Update tip stats
def update_tip_stats(user, tip, rain=False, giveaway=False):
	(User.update(
		tipped_amount=(User.tipped_amount + (tip / 1000000)),
		tip_count = User.tip_count + 1
		).where(User.user_id == user.user_id)
		).execute()
	if tip > int(float(user.top_tip)):
		(User.update(
			top_tip = tip,
			top_tip_ts = datetime.datetime.now()
			).where(User.user_id == user.user_id)
			).execute()
	if rain:
		(User.update(
			rain_amount = User.rain_amount + (tip / 1000000)
			)
			.where(User.user_id == user.user_id)
		).execute()
	elif giveaway:
		(User.update(
			giveaway_amount = User.giveaway_amount + (tip / 1000000)
			)
			.where(User.user_id == user.user_id)
		).execute()

def update_tip_total(user_id, new_total):
	user_id = str(user_id)
	User.update(tipped_amount = new_total).where(User.user_id == user_id).execute()
	return

def update_tip_count(user_id, new_count):
	user_id = str(user_id)
	User.update(tip_count = new_count).where(User.user_id == user_id).execute()
	return

def update_pending(user_id, send=0, receive=0):
	user_id=str(user_id)
	return (User.update(
			pending_send = (User.pending_send + send),
			pending_receive = (User.pending_receive + receive)
		    ).where(User.user_id == user_id)
		).execute()

def create_user(user_id, user_name, wallet_address):
	user_id=str(user_id)
	user = User(user_id=user_id,
		    user_name=user_name,
		    wallet_address=wallet_address,
		    )
	user.save()
	return user

### Transaction Stuff
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
	else:
		update_last_withdraw(src_usr.user_id)
	return tx

def update_last_withdraw(user_id):
	user_id = str(user_id)
	User.update(last_withdraw=datetime.datetime.now()).where(User.user_id == user_id).execute()

def get_last_withdraw_delta(user_id):
	user_id = str(user_id)
	try:
		user = User.select(User.last_withdraw).where(User.user_id == user_id).get()
		delta = (datetime.datetime.now() - user.last_withdraw).total_seconds()
		return delta
	except User.DoesNotExist:
		return None

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
		pending_receive += int(tx.amount)
	update_pending(winner_user_id, receive=pending_receive)
	(Transaction.update(
			to_address = winner.wallet_address,
			giveawayid = 0
		    ).where(
			(Transaction.giveawayid == giveaway_id)
	)).execute()
# Start Giveaway
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

def get_giveaway():
	try:
		giveaway = Giveaway.get(active=True)
		return giveaway
	except:
		return None

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

	return float(tip_sum)/ 1000000

def add_tip_to_giveaway(amount):
	giveawayupdt = (Giveaway
				.update(
					tip_amount = (Giveaway.tip_amount + amount)
				).where(Giveaway.active == True)
			).execute()

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
	user_id=str(user_id)
	banned = BannedUser.select().where(BannedUser.user_id == user_id).count()
	return banned > 0

def ban_user(user_id):
	user_id = str(user_id)
	already_banned = is_banned(user_id)
	if already_banned > 0:
		return False
	ban = BannedUser(user_id=user_id)
	ban.save()
	return True

def statsban_user(user_id):
	user_id = str(user_id)
	banned = User.update(stats_ban = True).where(User.user_id == user_id).execute()
	return banned > 0

def unban_user(user_id):
	user_id = str(user_id)
	deleted = BannedUser.delete().where(BannedUser.user_id == user_id).execute()
	return deleted > 0

def statsunban_user(user_id):
	user_id = str(user_id)
	unbanned = User.update(stats_ban = False).where(User.user_id == user_id).execute()
	return unbanned > 0

def get_banned():
	banned = BannedUser.select(BannedUser.user_id)
	users = User.select(User.user_name).where(User.user_id.in_(banned))
	if users.count() == 0:
		return "```Nobody Banned```"
	ret = "```"
	for idx,user in enumerate(users):
		ret += "%d: %s\n" % (idx+1,user.user_name)
	ret += "```"
	return ret

def get_statsbanned():
	statsbanned = User.select().where(User.stats_ban == True)
	if statsbanned.count() == 0:
		return "```No stats bans```"
	ret = "```"
	for idx,user in enumerate(statsbanned):
		ret += "%d: %s\n" % (idx+1,user.user_name)
	ret += "```"
	return ret

# Returns winning user
def finish_giveaway():
	contestants = Contestant.select(Contestant.user_id).where(Contestant.banned == False).order_by(fn.Random())
	contestant_ids = []
	for c in contestants:
		contestant_ids.append(c.user_id)
	shuffle(contestant_ids)
	offset = randint(0, len(contestant_ids) - 1)
	winner = get_user_by_id(contestant_ids[offset])
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
	user_id=str(user_id)
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
				"Giveaway fee: %d\n" +
				"Your donations: %d\n" +
				"Your ticket cost: %d\n\n" +
				"You may enter using `%sticket %d`") % (fee, contributions, cost, settings.command_prefix, cost)
		return return_str
	except Giveaway.DoesNotExist:
		contributions = get_tipgiveaway_contributions(user_id)
		return "There is no active giveaway.\nSo far you've contributed %d naneroo towards the next one!" % contributions

def contestant_exists(user_id):
	user_id = str(user_id)
	c = Contestant.select().where(Contestant.user_id == user_id).count()
	return c > 0

def is_active_giveaway():
	giveaway = Giveaway.select().where(Giveaway.active==True).count()
	if giveaway > 0:
		return True
	return False

# Return true if shadow banned, or banned in general
def ticket_spam_check(user_id, increment=True):
	user_id = str(user_id)
	user = get_user_by_id(user_id)
	if user is None:
		return False
	if is_banned(user_id):
		return True
	if increment:
		user.ticket_count += 1
		(User.update(
			ticket_count = (User.ticket_count + 1)
		     ).where(User.user_id == user_id)
		).execute()
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
	amount = fn.MAX(User.top_tip).alias('amount')
	top_24h = User.select(amount, User.user_name).where((User.top_tip_ts > past_dt) & (User.stats_ban == False)).order_by(User.top_tip_ts).limit(1)
	top_month = User.select(amount, User.user_name).where((fn.strftime("%m", User.top_tip_ts) == month_num) & (User.stats_ban == False)).order_by(User.top_tip_ts).limit(1)
	top_at = User.select(amount, User.user_name).where(User.stats_ban == False).order_by(User.top_tip_ts).limit(1)
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

# Marks TX as sent
def mark_transaction_sent(uuid, amt, source_id, target_id=None):
	tu = (Transaction.update(
			sent = True
		    ).where(
			(Transaction.uid == uuid) &
			(Transaction.sent == False)
	)).execute()
	if tu > 0:
		update_pending(source_id,send=amt)
		if target_id is not None:
			update_pending(target_id, receive=amt)

# This adds block to our TX
def mark_transaction_processed(uuid, tranid):
	(Transaction.update(
		tran_id = tranid,
		processed = True
	).where(Transaction.uid == uuid)).execute()

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
	if adjusted_count >= LAST_MSG_RAIN_WORDS and not is_private and (datetime.datetime.now() - user.last_msg_rain).total_seconds() > LAST_MSG_RAIN_DELTA:
		user.last_msg_count += 1
		user.last_msg_rain = datetime.datetime.now()
	user.last_msg=datetime.datetime.now()
	(User.update(
		last_msg_count = user.last_msg_count,
		last_msg_rain = user.last_msg_rain,
		last_msg = user.last_msg
	    ).where(User.user_id == user.user_id)
	).execute()
	return

def unicode_strip(content):
	pattern = re.compile("["
			u"\U0001F600-\U0001F64F"
			u"\U0001F300-\U0001F5FF"
			u"\U0001F1E0-\U0001F1FF"
			u"\U00002702-\U000027B0"
			u"\U000024C2-\U0001F251"
			"]+", flags=re.UNICODE)
	return pattern.sub(r'',content)

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

# Returns number of favorites deleted
def remove_favorite(user_id, favorite_id=None,identifier=None):

	if favorite_id is None and identifier is None:
		return 0
	user_id=str(user_id)
	favorite_id=str(favorite_id)
	deleted = 0
	if user_id is not None:
		deleted += UserFavorite.delete().where((UserFavorite.user_id == user_id) & (UserFavorite.favorite_id == favorite_id)).execute()
	if identifier is not None:
		deleted += UserFavorite.delete().where((UserFavorite.user_id == user_id) & (UserFavorite.identifier == identifier)).execute()
	return deleted

# Returns list of favorites for user ID
def get_favorites_list(user_id):
	user_id = str(user_id)
	favorites = UserFavorite.select().where(UserFavorite.user_id==user_id).order_by(UserFavorite.identifier)
	return_data = []
	for fav in favorites:
		return_data.append({'user_id':fav.favorite_id,'id': fav.identifier})
	return return_data

# User table
class User(Model):
	user_id = CharField(unique=True)
	user_name = CharField()
	wallet_address = CharField(unique=True)
	tipped_amount = FloatField(default=0.0, constraints=[SQL('DEFAULT 0.0')])
	pending_receive = IntegerField(default=0, constraints=[SQL('DEFAULT 0')])
	pending_send = IntegerField(default=0, constraints=[SQL('DEFAULT 0')])
	tip_count = IntegerField(default=0, constraints=[SQL('DEFAULT 0')])
	created = DateTimeField(default=datetime.datetime.now(), constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
	last_msg = DateTimeField(default=datetime.datetime.now(), constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
	last_msg_rain = DateTimeField(default=datetime.datetime.now(), constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
	last_msg_count = IntegerField(default=0, constraints=[SQL('DEFAULT 0')])
	top_tip = IntegerField(default=0, constraints=[SQL('DEFAULT 0')])
	top_tip_ts = DateTimeField(default=datetime.datetime.now(),constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
	ticket_count = IntegerField(default=0, constraints=[SQL('DEFAULT 0')])
	last_withdraw = DateTimeField(default=datetime.datetime.now(), constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
	stats_ban = BooleanField(default=False, constraints=[SQL('DEFAULT 0')])
	rain_amount = FloatField(default=0.0, constraints=[SQL('DEFAULT 0.0')])
	giveaway_amount = FloatField(default=0.0, constraints=[SQL('DEFAULT 0.0')])

	class Meta:
		database = db

# Transaction table, keep trac of sends to process
class Transaction(Model):
	uid = CharField(unique=True)
	source_address = CharField()
	to_address = CharField(null = True)
	amount = CharField()
	sent = BooleanField(default=False, constraints=[SQL('DEFAULT 0')])
	processed = BooleanField(default=False, constraints=[SQL('DEFAULT 0')])
	created = DateTimeField(default=datetime.datetime.now(), constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
	tran_id = CharField(default='', null=True)
	attempts = IntegerField(default=0, constraints=[SQL('DEFAULT 0')])
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

# Favorites List
class UserFavorite(Model):
	user_id = CharField()
	favorite_id = CharField()
	created = DateTimeField(default=datetime.datetime.now(),constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
	identifier = IntegerField() # Identifier makes it easy for user to remove this favorite

	class Meta:
		database = db

def create_db():
	db.connect()
	db.create_tables([User, Transaction, Giveaway, Contestant, BannedUser, UserFavorite], safe=True)
	logger.debug("DB Connected")

create_db()
