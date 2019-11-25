from tortoise.models import Model
from tortoise import fields
from util.env import Env

import datetime

class Stats(Model):
    user = fields.ForeignKeyField('db.User', related_name='stats', unique=True, index=True) 
    banned = fields.BooleanField(default=False)
    total_tips = fields.IntField(default=0)
    total_tipped_amount = fields.CharField(max_length=40, default='0')
    server_id = fields.BigIntField()
    top_tip = fields.CharField(max_length=40, default='0')
    top_tip_ts = fields.DatetimeField(auto_now_add=True)
    top_tip_month = fields.CharField(max_length=40, default='0')
    top_tip_month_ts = fields.DatetimeField(auto_now_add=True)
    top_tip_day = fields.CharField(max_length=40, default='0')
    top_tip_day_ts = fields.DatetimeField(auto_now_add=True)
    rain_amount = fields.CharField(max_length=40, default='0')
    giveaway_amount = fields.CharField(max_length=40, default='0')
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    async def update_tip_stats(self, amount: float, giveaway: bool = False, rain: bool = False):
        amount_raw = Env.amount_to_raw(amount)
        # Update total tipped amount and count
        self.total_tipped_amount = str(int(self.total_tipped_amount) + amount_raw)
        self.total_tips += 1
        # Update all time tip if necessary
        top_tip_updated = False
        if amount_raw > int(self.top_tip):
            self.top_tip = str(amount_raw)
            self.top_tip_ts = datetime.datetime.utcnow()
            top_tip_updated = True
        # Update monthly tip if necessary
        top_tip_month_updated = False
        if self.top_tip_month_ts.month != datetime.datetime.utcnow().month or amount_raw > int(self.top_tip_month):
            self.top_tip_month = str(amount_raw)
            self.top_tip_month_ts = datetime.datetime.utcnow()
            top_tip_month_updated = True
        # Update 24H tip if necessary
        top_tip_day_updated = False
        delta = datetime.datetime.utcnow() - self.top_tip_day_ts
        if delta.total_seconds() > 86400 or amount > int(self.top_tip_day):
            self.top_tip_day = str(amount_raw)
            self.top_tip_day_ts = datetime.datetime.utcnow()
            top_tip_day_updated = True
        # Update rain or giveaway stats
        rain_updated = False
        giveaway_updated = False
        if rain:
            self.rain_amount = str(int(self.rain_amount) + amount_raw)
            rain_updated = True
        elif giveaway:
            self.giveaway_amount = str(int(self.giveaway_amount) + amount_raw)
            giveaway_updated = True

        # Only update specific fields in save(), to avoid nuking the state potentially
        # It might be better to do Stats.filter(...).update() here, but this is easier to build into a single update
        update_fields = ['total_tipped_amount', 'total_tips']
        if top_tip_updated:
            update_fields.append('top_tip')
            update_fields.append('top_tip_ts')
        if top_tip_month_updated:
            update_fields.append('top_tip_month')
            update_fields.append('top_tip_month_ts')
        if top_tip_day_updated:
            update_fields.append('top_tip_day')
            update_fields.append('top_tip_day_ts')
        if rain_updated:
            update_fields.append('rain_amount')
        if giveaway_updated:
            update_fields.append('giveaway_amount')
        await self.save(
            update_fields=update_fields
        )