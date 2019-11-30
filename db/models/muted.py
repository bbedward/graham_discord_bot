from tortoise.models import Model
from tortoise import fields

import db.models.user as usr

class Muted(Model):
    user = fields.ForeignKeyField('db.User', related_name='muted', index=True)
    target_user = fields.ForeignKeyField('db.User', related_name='muted_by')

    class Meta:
        table = 'muted'

    @staticmethod
    async def mute_user(muted_by: usr.User, muted_target: usr.User):
        m = Muted(
            user = muted_by,
            target_user = muted_target
        )
        await m.save()