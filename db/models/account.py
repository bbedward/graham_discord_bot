from tortoise.models import Model
from tortoise import fields

class Account(Model):
    user = fields.ForeignKeyField('db.User', related_name='account', unique=True, index=True) # TODO - OneToOneField when tortoise supports this property
    address = fields.CharField(max_length=65, unique=True, index=True)

    class Meta:
        table = 'accounts'
