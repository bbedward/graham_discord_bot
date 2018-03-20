import datetime
import util
from peewee import *

# (Seconds) how long a user must wait in between messaging the bot
LAST_MSG_TIME = 1

db = SqliteDatabase('nanotipbot.db')

logger = util.get_logger("db")


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


def get_top_users(count):
    users = User.select().where(User.tipped_amount > 0).order_by(User.tipped_amount.desc()).limit(count)
    return_data = []
    for idx, user in enumerate(users):
        return_data.append({'index': idx + 1, 'name': user.user_name, 'amount': user.tipped_amount})
    return return_data


def create_user(user_id, user_name, wallet_address):
    user = User(user_id=user_id,
                user_name=user_name,
                wallet_address=wallet_address,
                tipped_amount=0.0,
                created=datetime.datetime.now(),
		last_msg=datetime.datetime.now()
                )
    user.save()
    return user

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
    with db.atomic() as transaction:
        try:
            if user is not None:
                user.last_msg=datetime.datetime.now()
                user.save()
            return
        except Exception as e:
            db.rollback()
            logger.exception(e)
            return

# Update tip amount for stats (this value is saved as NANO not xrb)
def update_tipped_amt(user_id, tipped_amt):
    with db.atomic() as transaction:
        try:
            user = get_user_by_id(user_id)
            if user is not None:
                user.tipped_amount += tipped_amt / 1000000
                user.save()
            return
        except Exception as e:
            db.rollback()
            logger.exception(e)
            return

# User table
class User(Model):
    user_id = CharField()
    user_name = CharField()
    wallet_address = CharField()
    tipped_amount = FloatField()
    created = DateTimeField()
    last_msg = DateTimeField()

    class Meta:
        database = db

def create_db():
    db.connect()
    db.create_tables([User], safe=True)


create_db()
