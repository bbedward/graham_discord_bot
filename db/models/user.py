from tortoise.models import Model
from tortoise import fields

class User(Model):
    id = fields.BigIntField(pk=True)
    user_name = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"
