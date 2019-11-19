from tortoise.models import Model
from tortoise import fields

banano = True

class Stats(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('db.User', related_name='stats')
    banned = fields.BooleanField(default=False)
    total_tips = fields.IntField()
    total_tipped_amount = fields.CharField(max_length=40)