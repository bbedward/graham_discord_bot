from tortoise.models import Model
from tortoise.transactions import in_transaction
from tortoise import fields
from rpc.client import RPCClient

class Account(Model):
    user = fields.ForeignKeyField('db.User', related_name='account', unique=True, index=True)
    address = fields.CharField(max_length=65, unique=True, index=True)
    pending_send = fields.CharField(max_length=40, default='0')
    pending_receive = fields.CharField(max_length=40, default='0')

    class Meta:
        table = 'accounts'
