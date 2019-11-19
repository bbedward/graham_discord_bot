from tortoise.models import Model
from tortoise import fields

class Secret(Model):
    id = fields.IntField(pk=True)
    seed = fields.CharField(max_length=128)

    class Meta:
        table = 'secrets'