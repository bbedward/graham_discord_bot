from dotenv import load_dotenv
load_dotenv()

# Unsupported script to migrate data from graham v3 to v4
from peewee import *
from playhouse.pool import PooledPostgresqlExtDatabase
from playhouse.shortcuts import model_to_dict
from tortoise.transactions import in_transaction

from db.tortoise_config import DBConfig
import db.models.user as usr
from db.models.stats import Stats
from db.models.account import Account

import asyncio
import os
import datetime
from util.number import NumberUtil
from util.env import Env

OLD_DB = os.getenv('OLD_DB')
OLD_DB_USER = os.getenv('OLD_DB_USER')
OLD_DB_PW = os.getenv('OLD_DB_PW')

print(OLD_DB)
print(OLD_DB_USER)
print(OLD_DB_PW)
# Old DB
db = PooledPostgresqlExtDatabase(OLD_DB, user=OLD_DB_USER, password=OLD_DB_PW, host='localhost', port=5432, max_connections=16)

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
	tip_count = IntegerField(default=0)
	created = DateTimeField(default=datetime.datetime.utcnow)
	top_tip = IntegerField(default=0)
	top_tip_ts = DateTimeField(default=datetime.datetime.utcnow)
	top_tip_month = IntegerField(default=0)
	top_tip_month_ts = DateTimeField(default=datetime.datetime.utcnow)
	top_tip_day = IntegerField(default=0)
	top_tip_day_ts = DateTimeField(default=datetime.datetime.utcnow)
	stats_ban = BooleanField(default=False)
	rain_amount = FloatField(default=0.0,)
	giveaway_amount = FloatField(default=0.0)

	class Meta:
		db_table='users'

# Banned List
class BannedUser(BaseModel):
	user_id = CharField()

# Separate table for frozen so we can freeze even users not registered with bot
class FrozenUser(BaseModel):
	user_id = IntegerField(unique=True)
	user_name = CharField()
	created = DateTimeField(default=datetime.datetime.utcnow)

### migration

async def do_migrate():
    await DBConfig().init_db()
    for u in User.select():
        print(f"Adding user {u.user_id}")
        frozen = FrozenUser.select().where(FrozenUser.user_id == int(u.user_id)).count() > 0
        banned = BannedUser.select().where(BannedUser.user_id == u.user_id).count() > 0
        async with in_transaction() as conn:
            user = usr.User(
                id = int(u.user_id),
                name = u.user_name.replace("`", ""),
                created_at = u.created,
                frozen = frozen,
                tip_banned = banned
            )
            await user.save(using_db=conn)
            # Create account
            account = Account(
                user = user,
                address = u.wallet_address
            )
            await account.save(using_db=conn)
            # Do stats
            stats = Stats(
                user=user,
                server_id=415935345075421194,
                banned=u.stats_ban,
                legacy_total_tipped_amount=NumberUtil.truncate_digits(float(u.tipped_amount), max_digits=Env.precision_digits()),
                total_tips=u.tip_count
            )
            await stats.save(using_db=conn)

if __name__ == "__main__":
    print("migration started")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(do_migrate())
    loop.close()
    print("migration done")