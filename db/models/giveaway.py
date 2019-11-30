from tortoise.models import Model
from tortoise import fields
from util.env import Env

class Giveaway(Model):
    started_by = fields.ForeignKeyField('db.User', related_name='started_giveaways', index=True, null=True)
    started_by_bot = fields.BooleanField(default=False)
    base_amount = fields.DecimalField(max_digits=20, decimal_places=Env.precision_digits(), default=0)
    donated_amount = fields.DecimalField(max_digits=20, decimal_places=Env.precision_digits(), default=0)
    winning_user = fields.ForeignKeyField('db.User', related_name='won_giveaways', null=True)

    class Meta:
        table = 'giveaways'