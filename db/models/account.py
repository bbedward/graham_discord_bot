from tortoise.models import Model
from tortoise import fields

class Account(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('db.User', related_name='account')
    address = fields.CharField(max_length=65, unique=True)
    pending_send = fields.CharField(max_length=40, default='0')
    pending_receive = fields.CharField(max_length=40, default='0')

    class Meta:
        table = 'accounts'