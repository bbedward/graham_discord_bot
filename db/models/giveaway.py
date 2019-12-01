from tortoise.models import Model
from tortoise import fields
from util.env import Env

import datetime
import db.models.user as usr

class Giveaway(Model):
    started_by = fields.ForeignKeyField('db.User', related_name='started_giveaways', index=True, null=True)
    started_by_bot = fields.BooleanField(default=False)
    base_amount = fields.CharField(max_length=50, default = '0')
    entry_fee = fields.CharField(max_length=50, default='0')
    end_at = fields.DatetimeField(null=True)
    ended_at = fields.DatetimeField(null=True)
    server_id = fields.BigIntField()
    started_in_channel = fields.BigIntField()
    winning_user = fields.ForeignKeyField('db.User', related_name='won_giveaways', null=True)

    class Meta:
        table = 'giveaways'

    @staticmethod
    async def get_active_giveaway(server_id: int) -> 'Giveaway':
        """Returns the current active giveaway"""
        giveaway = await Giveaway.filter(server_id=server_id, end_at__not_isnull=True).first()
        return giveaway


    @staticmethod
    async def start_giveaway_user(server_id: int, started_by: usr.User, amount: float, entry_fee: float, duration: int, started_in_channel: int, conn = None) -> 'Giveaway':
        # Double check no active giveaways
        active = await Giveaway.get_active_giveaway(server_id)
        if active is not None:
            raise Exception("There's already an active giveaway")
        giveaway = Giveaway(
            started_by=started_by,
            base_amount=Env.amount_to_raw(amount),
            entry_fee=Env.amount_to_raw(entry_fee),
            end_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=duration),
            server_id=server_id,
            started_in_channel=started_in_channel
        )
        await giveaway.save(using_db=conn)
        return giveaway