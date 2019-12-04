from db.redis import RedisDB
from tortoise.models import Model
from tortoise.transactions import in_transaction
from tortoise import fields
from util.env import Env
from util.number import NumberUtil

import asyncio
import datetime
import logging

class Stats(Model):
    user = fields.ForeignKeyField('db.User', related_name='stats', unique=True, index=True) 
    banned = fields.BooleanField(default=False)
    total_tips = fields.IntField(default=0)
    total_tipped_amount = fields.DecimalField(max_digits=20, decimal_places=Env.precision_digits(), default=0)
    legacy_total_tipped_amount = fields.DecimalField(max_digits=20, decimal_places=Env.precision_digits(), default=0)
    server_id = fields.BigIntField()
    top_tip = fields.DecimalField(max_digits=20, decimal_places=Env.precision_digits(), default=0)
    top_tip_at = fields.DatetimeField(auto_now_add=True)
    top_tip_month = fields.DecimalField(max_digits=20, decimal_places=Env.precision_digits(), default=0)
    top_tip_month_at = fields.DatetimeField(auto_now_add=True)
    top_tip_day = fields.DecimalField(max_digits=20, decimal_places=Env.precision_digits(), default=0)
    top_tip_day_at = fields.DatetimeField(auto_now_add=True)
    rain_amount = fields.DecimalField(max_digits=20, decimal_places=Env.precision_digits(), default=0)
    giveaway_amount = fields.DecimalField(max_digits=20, decimal_places=Env.precision_digits(), default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)
    stats_reset_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'server_id')

    async def update_tip_stats(self, amount: float, giveaway: bool = False, rain: bool = False):
        # TODO - would be better to do these updates atomically
        # https://github.com/tortoise/tortoise-orm/issues/245

        # Reset ballers list if it's a new year
        if self.stats_reset_at.year < datetime.datetime.utcnow().year:
            await Stats.all().update(total_tipped_amount=0, stats_reset_at=datetime.datetime.utcnow())

        # Update total tipped amount and count
        amount = NumberUtil.truncate_digits(amount, max_digits=Env.precision_digits())
        self.total_tipped_amount = NumberUtil.truncate_digits(float(self.total_tipped_amount) + amount, max_digits=Env.precision_digits())
        self.legacy_total_tipped_amount = NumberUtil.truncate_digits(float(self.legacy_total_tipped_amount) + amount, max_digits=Env.precision_digits())
        self.total_tips += 1
        # Update all time tip if necessary
        top_tip_updated = False
        if amount > self.top_tip:
            self.top_tip = amount
            self.top_tip_at = datetime.datetime.utcnow()
            top_tip_updated = True
        # Update monthly tip if necessary
        top_tip_month_updated = False
        if self.top_tip_month_at.month != datetime.datetime.utcnow().month or amount > self.top_tip_month:
            self.top_tip_month = amount
            self.top_tip_month_at = datetime.datetime.utcnow()
            top_tip_month_updated = True
        # Update 24H tip if necessary
        top_tip_day_updated = False
        delta = datetime.datetime.utcnow() - self.top_tip_day_at
        if delta.total_seconds() > 86400 or amount > self.top_tip_day:
            self.top_tip_day = amount
            self.top_tip_day_at = datetime.datetime.utcnow()
            top_tip_day_updated = True
        # Update rain or giveaway stats
        rain_updated = False
        giveaway_updated = False
        if rain:
            self.rain_amount = NumberUtil.truncate_digits(float(self.rain_amount) + amount, max_digits=Env.precision_digits())
            rain_updated = True
        elif giveaway:
            self.giveaway_amount = NumberUtil.truncate_digits(float(self.giveaway_amount) + amount, max_digits=Env.precision_digits())
            giveaway_updated = True

        async with in_transaction() as conn:
            update_fields = ['total_tipped_amount', 'legacy_total_tipped_amount', 'total_tips']
            if top_tip_updated:
                update_fields.append('top_tip')
                update_fields.append('top_tip_at')
            if top_tip_month_updated:
                update_fields.append('top_tip_month')
                update_fields.append('top_tip_month_at')
            if top_tip_day_updated:
                update_fields.append('top_tip_day')
                update_fields.append('top_tip_day_at')
            if rain_updated:
                update_fields.append('rain_amount')
            if giveaway_updated:
                update_fields.append('giveaway_amount')
            await self.save(
                update_fields=update_fields,
                using_db=conn
            )
