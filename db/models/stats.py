from tortoise.models import Model
from tortoise import fields

banano = True

class Stats(Model):
    user = fields.ForeignKeyField('db.User', related_name='stats', unique=True)
    banned = fields.BooleanField(default=False)
    total_tips = fields.IntField()
    total_tipped_amount = fields.CharField(max_length=40)
    modified_at = fields.DatetimeField(auto_now=True)