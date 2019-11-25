from tortoise.models import Model
from tortoise import fields

class Transaction(Model):
    sending_user = fields.ForeignKeyField('db.User', related_name='sent_transactions', index=True)
    receiving_user = fields.ForeignKeyField('db.User', related_name='received_transactions', null=True, index=True)
    destination = fields.CharField(max_length=65)
    block_hash = fields.CharField(max_length=64, index=True)
    amount = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'transactions'
