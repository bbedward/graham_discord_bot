from tortoise.models import Model
from tortoise import fields

class Account(Model):
    user = fields.OneToOneField('db.User', related_name='account', db_index=True)
    address = fields.CharField(max_length=65, unique=True, db_index=True)

    class Meta:
        table = 'accounts'
