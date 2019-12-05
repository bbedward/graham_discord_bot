from tortoise.models import Model
from tortoise import fields
from typing import List
from util.env import Env

import datetime
import db.models.user as usr

class Giveaway(Model):
    started_by = fields.ForeignKeyField('db.User', related_name='started_giveaways', index=True, null=True)
    started_by_bot = fields.BooleanField(default=False)
    base_amount = fields.CharField(max_length=50, default = '0')
    final_amount = fields.CharField(max_length=50, default = '0', null=True)
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
        """Returns the current active giveaway for the server, if there is one."""
        giveaway = await Giveaway.filter(server_id=server_id, end_at__not_isnull=True, winning_user=None).prefetch_related('started_by').order_by('-end_at').first()
        return giveaway

    @staticmethod
    async def get_active_giveaway_by_id(id: int) -> 'Giveaway':
        """Returns the active giveaway by id, if there is one."""
        giveaway = await Giveaway.filter(id=id, end_at__not_isnull=True, winning_user=None).prefetch_related('started_by').order_by('-end_at').first()
        return giveaway

    @staticmethod
    async def get_active_giveaways(server_ids: List[int]) -> List['Giveaway']:
        """Returns the current active giveaway, if there is one."""
        giveaway = await Giveaway.filter(server_id__in=server_ids, end_at__not_isnull=True, winning_user=None).prefetch_related('started_by').order_by('-end_at')
        return giveaway

    @staticmethod
    async def get_pending_bot_giveaway(server_id: int) -> 'Giveaway':
        """Return the current pending bot giveaway, if there is one"""
        return await Giveaway.filter(server_id=server_id, end_at__isnull=True, started_by_bot=True).order_by('-end_at').first()

    @staticmethod
    async def start_giveaway_user(server_id: int, started_by: usr.User, amount: float, entry_fee: float, duration: int, started_in_channel: int, conn = None) -> 'Giveaway':
        # Double check no active giveaways
        active = await Giveaway.get_active_giveaway(server_id)
        if active is not None:
            raise Exception("There's already an active giveaway")
        giveaway = Giveaway(
            started_by=started_by,
            base_amount=str(Env.amount_to_raw(amount)),
            entry_fee=str(Env.amount_to_raw(entry_fee)),
            end_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=duration),
            server_id=server_id,
            started_in_channel=started_in_channel
        )
        await giveaway.save(using_db=conn)
        return giveaway

    @staticmethod
    async def start_giveaway_bot(server_id: int, entry_fee: float, started_in_channel: int, conn = None) -> 'Giveaway':
        # Double check no active giveaways
        active = await Giveaway.get_active_giveaway(server_id)
        if active is not None:
            raise Exception("There's already an active giveaway")
        giveaway = Giveaway(
            started_by_bot=True,
            base_amount=str(Env.amount_to_raw(0)),
            entry_fee=str(Env.amount_to_raw(entry_fee)),
            server_id=server_id,
            started_in_channel=started_in_channel
        )
        await giveaway.save(using_db=conn)
        return giveaway

    async def get_transactions(self):
        """Get transactions belonging to this giveaway"""
        return await self.giveaway_transactions.all()