from tortoise.models import Model
from tortoise import fields

class Account(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('db.User', related_name='account')
    seed_index = fields.BigIntField(unique=True) # The index this account is on the seed
    pending_send = fields.CharField(max_length=40)
    pending_receive = fields.CharField(max_length=40)

    class Meta:
        table = 'accounts'